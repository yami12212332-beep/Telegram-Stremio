"""Bridge to a third-party Telegram file-search bot (M Searcher).

The bot cannot be called through the Bot API: Telegram does not deliver messages
from one bot to another. This module drives it through the user account session
("Userbot") that is already used by Global Search.

Flow:
    query -> userbot sends a DM -> poll for the result keyboard -> user picks a
    result in the addon -> click the button -> poll for the document -> copy it
    into the staging channel -> the normal receiver indexes it / it streams
    directly through /dl.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

from pyrogram.errors import FloodWait
from pyrogram.types import Message

import Backend.pyrofork.bot as botmod
from Backend.helper.settings_manager import SettingsManager
from Backend.logger import LOGGER


#----- Tunables
_SEARCH_CACHE_TTL = 300
_REQUEST_TTL = 2 * 60 * 60
_REQUEST_MAX = 2000
_POLL_INTERVAL = 1.0
_SEARCH_LOCK = asyncio.Lock()

_SIZE_RE = re.compile(r"[\[《<【]\s*([\d.]+\s*(?:GB|MB))\s*[\]》>】]", re.IGNORECASE)
_QUALITY_RE = re.compile(r"\b(2160p?|1440p?|1080p?|720p?|480p?|360p?)\b", re.IGNORECASE)
_TAMIL_RE = re.compile(r"\b(tamil|tam)\b", re.IGNORECASE)
_SEASON_EPISODE_RE = re.compile(r"\bS(\d{1,3})\s*[Ee]P?\s*(\d{1,4})\b")
_EPISODE_ONLY_RE = re.compile(r"\bE(?:P)?\s*(\d{1,4})\b", re.IGNORECASE)
_SEASON_ONLY_RE = re.compile(r"\bS(\d{1,3})\b", re.IGNORECASE)
_NO_RESULTS_RE = re.compile(
    r"no results|not found|couldn'?t find|no matches|retry with the correct spelling",
    re.IGNORECASE,
)
_AUDIO_RE = re.compile(
    r"\b(tamil|telugu|hindi|malayalam|kannada|english|multi(?:\s*audio)?)\b",
    re.IGNORECASE,
)
_QUALITY_ORDER = {"2160p": 6, "1440p": 5, "1080p": 4, "720p": 3, "480p": 2, "360p": 1}


class ExternalSearchError(RuntimeError):
    """The bridge could not complete a request."""


class ExternalSearchBusy(ExternalSearchError):
    """Telegram asked us to wait (FloodWait) or another search is running."""

    def __init__(self, wait_seconds: int = 5, message: str = "M Searcher is busy"):
        super().__init__(message)
        self.wait = max(1, int(wait_seconds))


class ExternalSearchEmpty(ExternalSearchError):
    """The source bot explicitly reported that it has no results."""


@dataclass
class Candidate:
    """One file option parsed from the source bot's result keyboard."""

    label: str
    size: str
    quality: str
    audio: str
    tamil: bool
    row: int
    col: int
    callback_data: str = ""
    chat_id: int = 0
    message_id: int = 0
    season: Optional[int] = None
    episode: Optional[int] = None


@dataclass
class ExternalRequest:
    """A candidate plus everything needed to resolve and stream it later."""

    request_id: str
    token: str
    chat_id: int
    message_id: int
    row: int
    col: int
    label: str
    quality: str
    size: str
    audio: str
    tamil: bool
    callback_data: str
    title: str
    created_at: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    resolved_chat_id: Optional[int] = None
    resolved_message_id: Optional[int] = None
    filename: str = ""


_SEARCH_CACHE: dict[str, tuple[float, List[Candidate]]] = {}
_REQUESTS: dict[str, ExternalRequest] = {}
_WARNED: set[str] = set()


#----- Log a condition once instead of on every addon request
def _warn_once(key: str, message: str) -> None:
    if key in _WARNED:
        return
    _WARNED.add(key)
    LOGGER.warning(f"[MSEARCH] {message}")


#----- Current bridge configuration, or a clear reason why it is unavailable
def _config():
    settings = SettingsManager.current()
    if not settings.external_search:
        raise ExternalSearchError("M Searcher bridge is disabled (external_search)")
    if not settings.external_bot:
        raise ExternalSearchError("M Searcher bot username is not configured (external_bot)")
    if not settings.staging_channel:
        raise ExternalSearchError("Staging channel is not configured (staging_channel)")
    if botmod.Userbot is None:
        raise ExternalSearchError("No Telegram user session is connected (Userbot)")
    return settings


#----- Normalize a title for a stable cache key
def _cache_key(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip().lower()


#----- Build a title/year/SxxExx query for the source bot
def build_query(title: str, year: Optional[int] = None,
                season: Optional[int] = None, episode: Optional[int] = None) -> str:
    variants = build_query_variants(title, year, season, episode)
    return variants[0] if variants else ""


#----- Ordered query variants, most specific first
def build_query_variants(title: str, year: Optional[int] = None,
                         season: Optional[int] = None,
                         episode: Optional[int] = None) -> List[str]:
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not title:
        return []
    title = title[:140]

    if season is not None and episode is not None:
        try:
            season = int(season)
            episode = int(episode)
            # Source bots are inconsistent: some index "S01E01", others "S01 EP01".
            # Always try the compact form first, then the spaced form, then the season.
            return [
                f"{title} S{season:02d}E{episode:02d}",
                f"{title} S{season:02d} EP{episode:02d}",
                f"{title} S{season:02d}",
                title,
            ]
        except (TypeError, ValueError):
            return [title]

    if year:
        return [f"{title} {year}", title]
    return [title]


#----- Parse one button label like "《1.67 GB》 House ... 1080p S03E02"
def parse_candidate(text: str, row: int, col: int) -> Optional[Candidate]:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw:
        return None

    size_match = _SIZE_RE.search(raw)
    quality_match = _QUALITY_RE.search(raw)
    if not size_match and not quality_match:
        return None

    size = re.sub(r"\s+", "", size_match.group(1)) if size_match else ""
    quality = quality_match.group(1).lower() if quality_match else ""
    if quality and not quality.endswith("p"):
        quality += "p"
    label = _SIZE_RE.sub("", raw).strip(" -–—|·")
    audio_match = _AUDIO_RE.search(label)
    audio = audio_match.group(1).lower() if audio_match else ""

    season = episode = None
    episode_match = _SEASON_EPISODE_RE.search(label)
    if episode_match:
        season = int(episode_match.group(1))
        episode = int(episode_match.group(2))
    else:
        episode_match = _EPISODE_ONLY_RE.search(label)
        if episode_match:
            episode = int(episode_match.group(1))
        season_match = _SEASON_ONLY_RE.search(label)
        if season_match:
            season = int(season_match.group(1))

    return Candidate(
        label=label or raw,
        size=size,
        quality=quality,
        audio=audio,
        tamil=bool(_TAMIL_RE.search(label)) or audio == "tamil",
        row=row,
        col=col,
        season=season,
        episode=episode,
    )


#----- Pull every parseable file button out of one message
def candidates_from_message(message: Message) -> List[Candidate]:
    markup = getattr(message, "reply_markup", None)
    rows = getattr(markup, "inline_keyboard", None) or []
    found: List[Candidate] = []
    for row_idx, row in enumerate(rows):
        for col_idx, button in enumerate(row or []):
            if getattr(button, "callback_data", None) is None:
                continue  # URL buttons cannot be clicked by the userbot
            candidate = parse_candidate(getattr(button, "text", ""), row_idx, col_idx)
            if candidate:
                candidate.callback_data = str(button.callback_data)
                candidate.chat_id = int(message.chat.id)
                candidate.message_id = int(message.id)
                found.append(candidate)
    return found


#----- Find the exact button again, even if the bot edited/paginated the message
def find_button(message: Message, callback_data: str, fallback: tuple[int, int]):
    markup = getattr(message, "reply_markup", None)
    rows = getattr(markup, "inline_keyboard", None) or []
    if callback_data:
        for row_idx, row in enumerate(rows):
            for col_idx, button in enumerate(row or []):
                if str(getattr(button, "callback_data", "")) == callback_data:
                    return row_idx, col_idx
        raise ExternalSearchError("The M Searcher result list changed; reopen the title")
    return fallback


#----- Size helper used only for ranking
def _size_bytes(size: str) -> int:
    match = re.match(r"([\d.]+)\s*(GB|MB)", size or "", re.IGNORECASE)
    if not match:
        return 0
    try:
        value = float(match.group(1))
    except ValueError:
        return 0
    return int(value * (1024 ** 3 if match.group(2).upper() == "GB" else 1024 ** 2))


#----- Prefer Tamil, then better quality, then larger files
def select_candidates(candidates: List[Candidate], *, per_quality: int = 1,
                      tamil_first: bool = True, max_results: int = 6,
                      season: Optional[int] = None,
                      episode: Optional[int] = None) -> List[Candidate]:
    if not candidates:
        return []

    pool = list(candidates)

    #----- Never offer an episode other than the one the player asked for
    if episode is not None:
        wanted_episode = int(episode)
        wanted_season = int(season) if season is not None else None
        pool = [
            candidate for candidate in pool
            if candidate.episode == wanted_episode
            and (wanted_season is None or candidate.season is None
                 or candidate.season == wanted_season)
        ]
        if not pool:
            return []
    elif season is not None:
        wanted_season = int(season)
        pool = [
            candidate for candidate in pool
            if candidate.season is None or candidate.season == wanted_season
        ]
        if not pool:
            return []

    def rank(c: Candidate):
        return (
            0 if (c.tamil and tamil_first) else 1,
            -_QUALITY_ORDER.get(c.quality, 0),
            -_size_bytes(c.size),
            c.label.lower(),
        )

    ordered = sorted(pool, key=rank)
    per_quality = max(0, int(per_quality))  # 0 = every available source
    max_results = max(1, int(max_results))

    counts: dict[str, int] = {}
    seen: set[tuple[str, str, str]] = set()
    selected: List[Candidate] = []
    for candidate in ordered:
        quality = candidate.quality or "hd"
        if per_quality and counts.get(quality, 0) >= per_quality:
            continue
        key = (quality, candidate.size, candidate.label.lower())
        if key in seen:
            continue
        seen.add(key)
        counts[quality] = counts.get(quality, 0) + 1
        selected.append(candidate)
        if len(selected) >= max_results:
            break
    return selected


#----- Resolve the configured bot username/id to a chat object
async def _resolve_bot(userbot, username: str):
    target = int(username) if username.lstrip("-").isdigit() else username
    try:
        return await userbot.get_users(target)
    except Exception as exc:
        raise ExternalSearchError(f"Cannot resolve M Searcher bot '{username}': {exc}") from exc


#----- Get messages from the bot chat, tolerating transient errors
async def _history(userbot, chat_id: int, limit: int = 12) -> List[Message]:
    messages: List[Message] = []
    try:
        async for message in userbot.get_chat_history(chat_id, limit=limit):
            messages.append(message)
    except FloodWait as exc:
        raise ExternalSearchBusy(exc.value, f"Telegram asks to wait {exc.value}s") from exc
    except Exception as exc:
        _warn_once("history", f"Could not read the M Searcher chat: {exc}")
    return messages


#----- Wait until the bot posts/edits a message containing file buttons
async def _wait_for_results(userbot, chat_id: int, bot_id: int, sent: Message,
                            deadline: float):
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)
        for message in await _history(userbot, chat_id):
            if not getattr(message, "from_user", None) or message.from_user.id != bot_id:
                continue
            try:
                edited_after_send = (
                    getattr(message, "edit_date", None) is not None
                    and message.edit_date >= sent.date
                )
            except TypeError:
                edited_after_send = getattr(message, "edit_date", None) is not None
            if message.id < sent.id and not edited_after_send:
                continue
            found = candidates_from_message(message)
            if found:
                return message, found
            # Single match: the bot sends the file directly instead of a list.
            if message.id > sent.id:
                direct = candidate_from_file(message)
                if direct:
                    return message, [direct]
                text = getattr(message, "text", "") or ""
                if _NO_RESULTS_RE.search(text):
                    raise ExternalSearchEmpty(
                        re.sub(r"\s+", " ", text).strip()[:160] or "M Searcher found no results"
                    )
    raise ExternalSearchError("M Searcher did not return file options in time")


#----- Search the source bot (cached) and return all parsed file options
async def _search_message(query: str, timeout: int):
    settings = SettingsManager.current()
    userbot = botmod.Userbot
    bot = await _resolve_bot(userbot, settings.external_bot)
    try:
        sent = await userbot.send_message(bot.id, query)
    except FloodWait as exc:
        raise ExternalSearchBusy(exc.value) from exc

    deadline = time.monotonic() + timeout
    return await _wait_for_results(userbot, bot.id, bot.id, sent, deadline)


#----- Does a candidate belong to the requested season/episode?
def _episode_match(candidate: Candidate, season: Optional[int], episode: int) -> bool:
    if candidate.episode != episode:
        return False
    return season is None or candidate.season is None or candidate.season == season


#----- Locate a "Next" button and return Pyrogram's (column, row)
def _next_button(message: Message):
    markup = getattr(message, "reply_markup", None)
    rows = getattr(markup, "inline_keyboard", None) or []
    for row_idx, row in enumerate(rows):
        for col_idx, button in enumerate(row or []):
            text = (getattr(button, "text", "") or "").lower()
            if "next" in text and getattr(button, "callback_data", None):
                return col_idx, row_idx
    return None


#----- Episode query forms; source bots index either S01E01 or S01 EP01
def build_episode_queries(title: str, season: int, episode: int) -> List[str]:
    title = re.sub(r"\s+", " ", str(title or "")).strip()[:140]
    if not title:
        return []
    try:
        season, episode = int(season), int(episode)
    except (TypeError, ValueError):
        return [title]

    queries = [
        f"{title} S{season:02d}E{episode:02d}",
        f"{title} S{season:02d}E{episode}",
        f"{title} S{season:02d} EP{episode:02d}",
        f"{title} S{season:02d}",
    ]
    return list(dict.fromkeys(queries))


def _is_episode_query(query: str) -> bool:
    return bool(_SEASON_EPISODE_RE.search(query) or _EPISODE_ONLY_RE.search(query))


#----- Walk the result pages until the requested episode shows up
async def _paginate_for_episode(userbot, chat_id: int, message: Message,
                                season: Optional[int], episode: int, *,
                                max_pages: int = 5, deadline: float) -> List[Candidate]:
    seen: set[str] = set()
    for _ in range(max_pages):
        matches = [
            candidate for candidate in candidates_from_message(message)
            if _episode_match(candidate, season, episode)
        ]
        if matches:
            return matches
        if time.monotonic() >= deadline:
            break

        button = _next_button(message)
        if not button:
            break
        col, row = button
        markup = getattr(message, "reply_markup", None)
        rows = getattr(markup, "inline_keyboard", None) or []
        callback = ""
        try:
            callback = str(rows[row][col].callback_data)
        except (IndexError, AttributeError):
            pass
        if callback and callback in seen:
            break
        if callback:
            seen.add(callback)

        old_text = (getattr(message, "text", "") or "")[:200]
        try:
            await message.click(col, row)
        except FloodWait as exc:
            raise ExternalSearchBusy(exc.value) from exc
        except Exception as exc:
            _warn_once("pagination", f"Could not page M Searcher results: {exc}")
            break

        fresh = None
        edit_deadline = min(deadline, time.monotonic() + 4)
        while time.monotonic() < edit_deadline:
            await asyncio.sleep(0.5)
            try:
                fresh = await userbot.get_messages(chat_id, message_ids=message.id)
            except FloodWait as exc:
                raise ExternalSearchBusy(exc.value) from exc
            except Exception:
                fresh = None
            if fresh and (getattr(fresh, "text", "") or "")[:200] != old_text:
                break
        if not fresh:
            break
        message = fresh

    return [
        candidate for candidate in candidates_from_message(message)
        if _episode_match(candidate, season, episode)
    ]


async def search_candidates(query: str, *, timeout: Optional[int] = None) -> List[Candidate]:
    settings = _config()
    key = _cache_key(query)
    if not key:
        return []

    cached = _SEARCH_CACHE.get(key)
    if cached and time.time() - cached[0] < _SEARCH_CACHE_TTL:
        return list(cached[1])

    timeout = max(1, min(30, int(timeout or settings.external_timeout)))
    try:
        await asyncio.wait_for(_SEARCH_LOCK.acquire(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise ExternalSearchBusy(3, "Another M Searcher request is running") from exc

    try:
        # Another task may have filled the cache while we waited.
        cached = _SEARCH_CACHE.get(key)
        if cached and time.time() - cached[0] < _SEARCH_CACHE_TTL:
            return list(cached[1])

        _, candidates = await _search_message(query, timeout)

        _SEARCH_CACHE[key] = (time.time(), candidates)
        LOGGER.info(f"[MSEARCH] '{query}' -> {len(candidates)} option(s)")
        return list(candidates)
    finally:
        _SEARCH_LOCK.release()


#----- Walk every result page and aggregate the file buttons
async def _collect_pages(userbot, chat_id: int, message: Message, *,
                         max_pages: int = 5, deadline: float) -> List[Candidate]:
    collected: List[Candidate] = []
    seen: set[tuple] = set()
    seen_next: set[str] = set()

    def add_from(msg: Message) -> None:
        for candidate in candidates_from_message(msg):
            key = (candidate.label, candidate.size, candidate.quality,
                   candidate.callback_data or candidate.message_id)
            if key not in seen:
                seen.add(key)
                collected.append(candidate)

    add_from(message)
    for _ in range(max(0, max_pages - 1)):
        if time.monotonic() >= deadline:
            break

        button = _next_button(message)
        if not button:
            break
        col, row = button
        markup = getattr(message, "reply_markup", None)
        rows = getattr(markup, "inline_keyboard", None) or []
        try:
            callback = str(rows[row][col].callback_data)
        except (IndexError, AttributeError):
            callback = ""
        if callback and callback in seen_next:
            break
        if callback:
            seen_next.add(callback)

        old_text = (getattr(message, "text", "") or "")[:200]
        try:
            await message.click(col, row)
        except FloodWait as exc:
            raise ExternalSearchBusy(exc.value) from exc
        except Exception as exc:
            _warn_once("pagination", f"Could not page M Searcher results: {exc}")
            break

        fresh = None
        edit_deadline = min(deadline, time.monotonic() + 4)
        while time.monotonic() < edit_deadline:
            await asyncio.sleep(0.5)
            try:
                fresh = await userbot.get_messages(chat_id, message_ids=message.id)
            except FloodWait as exc:
                raise ExternalSearchBusy(exc.value) from exc
            except Exception:
                fresh = None
            if fresh and (getattr(fresh, "text", "") or "")[:200] != old_text:
                break
        if not fresh:
            break
        message = fresh
        add_from(message)

    return collected


async def search_all(title: str, year: Optional[int] = None, *,
                     timeout: Optional[int] = None,
                     max_pages: int = 5) -> List[Candidate]:
    """Movie-style search: collect every file across the bot's result pages."""
    settings = _config()
    key = f"all:{_cache_key(title)}:{year}"
    cached = _SEARCH_CACHE.get(key)
    if cached and time.time() - cached[0] < _SEARCH_CACHE_TTL:
        return list(cached[1])

    timeout = max(8, min(60, int(timeout or settings.external_timeout + 10)))
    try:
        await asyncio.wait_for(_SEARCH_LOCK.acquire(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise ExternalSearchBusy(3, "Another M Searcher request is running") from exc

    try:
        cached = _SEARCH_CACHE.get(key)
        if cached and time.time() - cached[0] < _SEARCH_CACHE_TTL:
            return list(cached[1])

        userbot = botmod.Userbot
        deadline = time.monotonic() + timeout
        for query in build_query_variants(title, year):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                message, candidates = await _search_message(
                    query, max(1, min(int(remaining), settings.external_timeout))
                )
            except ExternalSearchEmpty as exc:
                LOGGER.info(f"[MSEARCH] '{query}' -> {exc}")
                continue

            if not candidates:
                continue
            collected = await _collect_pages(
                userbot, message.chat.id, message,
                max_pages=max_pages, deadline=deadline,
            )
            if collected:
                _SEARCH_CACHE[key] = (time.time(), collected)
                LOGGER.info(f"[MSEARCH] '{query}' -> {len(collected)} option(s) across pages")
                return collected
        return []
    finally:
        _SEARCH_LOCK.release()


#----- Find one episode, paging through season-wide results when needed
async def search_episode(title: str, season: int, episode: int, *,
                         timeout: Optional[int] = None) -> List[Candidate]:
    settings = _config()
    key = f"episode:{_cache_key(title)}:{season}:{episode}"
    cached = _SEARCH_CACHE.get(key)
    if cached and time.time() - cached[0] < _SEARCH_CACHE_TTL:
        return list(cached[1])

    timeout = max(8, min(60, int(timeout or settings.external_timeout + 10)))
    try:
        await asyncio.wait_for(_SEARCH_LOCK.acquire(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise ExternalSearchBusy(3, "Another M Searcher request is running") from exc

    try:
        cached = _SEARCH_CACHE.get(key)
        if cached and time.time() - cached[0] < _SEARCH_CACHE_TTL:
            return list(cached[1])

        userbot = botmod.Userbot
        deadline = time.monotonic() + timeout
        for query in build_episode_queries(title, season, episode):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                message, candidates = await _search_message(
                    query, max(1, min(int(remaining), settings.external_timeout))
                )
            except ExternalSearchEmpty as exc:
                LOGGER.info(f"[MSEARCH] '{query}' -> {exc}")
                continue

            matches = [
                candidate for candidate in candidates
                if _episode_match(candidate, season, episode)
            ]
            if not matches and _is_episode_query(query):
                matches = await _paginate_for_episode(
                    userbot, message.chat.id, message, season, episode, deadline=deadline,
                )

            if matches:
                _SEARCH_CACHE[key] = (time.time(), matches)
                LOGGER.info(f"[MSEARCH] '{query}' -> {len(matches)} episode option(s)")
                return list(matches)
        return []
    finally:
        _SEARCH_LOCK.release()


#----- Try the specific query first, then progressively broader ones
async def search_best(title: str, year: Optional[int] = None,
                      season: Optional[int] = None, episode: Optional[int] = None,
                      *, timeout: Optional[int] = None) -> List[Candidate]:
    settings = _config()
    timeout = max(3, min(30, int(timeout or settings.external_timeout)))
    deadline = time.monotonic() + timeout

    for query in build_query_variants(title, year, season, episode):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            candidates = await search_candidates(query, timeout=max(1, int(remaining)))
        except ExternalSearchEmpty as exc:
            LOGGER.info(f"[MSEARCH] '{query}' -> {exc}")
            continue
        if candidates:
            return candidates
    return []


#----- Click one result and wait for the bot to send the actual file
async def _click_and_wait(request: ExternalRequest, *, timeout: int) -> Message:
    userbot = botmod.Userbot
    if userbot is None:
        raise ExternalSearchError("No Telegram user session is connected")

    try:
        message = await userbot.get_messages(request.chat_id, message_ids=request.message_id)
    except FloodWait as exc:
        raise ExternalSearchBusy(exc.value) from exc
    except Exception as exc:
        raise ExternalSearchError(f"Could not load the M Searcher result message: {exc}") from exc

    if message is None:
        raise ExternalSearchError("The M Searcher result message no longer exists")

    row, col = find_button(message, request.callback_data, (request.row, request.col))
    try:
        # Pyrogram's click(x, y) takes (column, row), unlike our (row, col) naming.
        await message.click(col, row)
    except FloodWait as exc:
        raise ExternalSearchBusy(exc.value) from exc
    except Exception as exc:
        raise ExternalSearchError(f"Could not select the result: {exc}") from exc

    deadline = time.monotonic() + timeout
    baseline = max(message.id, request.message_id)
    last_text = ""
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)

        for item in await _history(userbot, request.chat_id):
            if item.id > baseline and (item.document or item.video):
                return item

        # Some bots edit the result message into the file instead of sending a new one.
        try:
            fresh = await userbot.get_messages(request.chat_id, message_ids=request.message_id)
        except Exception:
            fresh = None
        if fresh and (fresh.document or fresh.video):
            return fresh
        if fresh and fresh.text:
            last_text = re.sub(r"\s+", " ", fresh.text)[:160]

    detail = f": {last_text}" if last_text else ""
    raise ExternalSearchError(f"M Searcher did not send the file in time{detail}")


#----- Copy the file into our own staging channel (server-side on Telegram)
async def _copy_to_staging(file_message: Message, caption: str = "") -> Message:
    settings = SettingsManager.current()
    staging = settings.staging_channel
    if not staging:
        raise ExternalSearchError("Staging channel is not configured")
    if not staging.startswith("-100") or not staging[4:].isdigit():
        raise ExternalSearchError("Staging channel must be a -100xxxxxxxxxx channel id")

    userbot = botmod.Userbot
    if userbot is None:
        raise ExternalSearchError("No Telegram user session is connected")

    try:
        target = int(staging)
    except (TypeError, ValueError) as exc:
        raise ExternalSearchError(f"Invalid staging channel id: {staging}") from exc

    try:
        copied = await userbot.copy_message(
            chat_id=target,
            from_chat_id=file_message.chat.id,
            message_id=file_message.id,
            caption=caption or None,
        )
    except FloodWait as exc:
        raise ExternalSearchBusy(exc.value) from exc
    except Exception as exc:
        raise ExternalSearchError(
            "Could not copy the file to the staging channel "
            f"(protected content or missing permission): {exc}"
        ) from exc

    if copied is None:
        raise ExternalSearchError("Telegram returned no copied message")
    LOGGER.info(f"[MSEARCH] Copied message {file_message.id} to staging channel {staging}")
    return copied


#----- Filename of a Telegram media message
def _filename(message: Message) -> str:
    document = getattr(message, "document", None)
    video = getattr(message, "video", None)
    if document and document.file_name:
        return document.file_name
    if video and video.file_name:
        return video.file_name
    return "video.mkv"


#----- Human-readable size for a file message
def _human_size(num) -> str:
    try:
        num = int(num or 0)
    except (TypeError, ValueError):
        return ""
    if num <= 0:
        return ""
    if num >= 1024 ** 3:
        return f"{num / (1024 ** 3):.2f}GB"
    return f"{num / (1024 ** 2):.2f}MB"


#----- Treat a file the bot sent directly (single match) as one candidate
def candidate_from_file(message: Message) -> Optional[Candidate]:
    if not (getattr(message, "document", None) or getattr(message, "video", None)):
        return None
    name = _filename(message)
    size_bytes = (
        getattr(getattr(message, "document", None), "file_size", 0)
        or getattr(getattr(message, "video", None), "file_size", 0)
        or 0
    )
    candidate = parse_candidate(name, 0, 0) or Candidate(
        label=name, size="", quality="", audio="", tamil=False, row=0, col=0
    )
    candidate.label = name or candidate.label
    candidate.size = _human_size(size_bytes) or candidate.size
    candidate.callback_data = ""  # no button: copy this message directly
    candidate.chat_id = int(message.chat.id)
    candidate.message_id = int(message.id)
    return candidate


#----- Load a file that arrived without a button click
async def _load_direct_file(request: ExternalRequest) -> Message:
    userbot = botmod.Userbot
    if userbot is None:
        raise ExternalSearchError("No Telegram user session is connected")

    try:
        message = await userbot.get_messages(request.chat_id, message_ids=request.message_id)
    except FloodWait as exc:
        raise ExternalSearchBusy(exc.value) from exc
    except Exception as exc:
        raise ExternalSearchError(f"Could not load the M Searcher file message: {exc}") from exc

    if message is None:
        raise ExternalSearchError("The M Searcher file message no longer exists")
    if not (getattr(message, "document", None) or getattr(message, "video", None)):
        raise ExternalSearchError("The M Searcher message is not a file")
    return message


#----- Resolve one registered candidate exactly once (safe to call repeatedly)
async def prepare_request(request: ExternalRequest) -> ExternalRequest:
    async with request.lock:
        if request.resolved_message_id and request.resolved_chat_id:
            return request

        settings = SettingsManager.current()
        timeout = max(10, min(60, settings.external_timeout + 10))

        if request.callback_data:
            file_message = await _click_and_wait(request, timeout=timeout)
        else:
            # The bot answered the search with the file itself (single match).
            file_message = await _load_direct_file(request)
        caption = request.label[:1000]
        if request.size and request.size.lower() not in caption.lower():
            caption = f"{caption} {request.size}"[:1000]
        copied = await _copy_to_staging(file_message, caption=caption)

        request.resolved_chat_id = copied.chat.id
        request.resolved_message_id = copied.id
        request.filename = _filename(file_message)
        return request


#----- Stable, non-reversible request id (tied to the addon token and button)
def _make_request_id(token: str, chat_id: int, message_id: int, row: int, col: int,
                     label: str = "", size: str = "") -> str:
    raw = f"{token}:{chat_id}:{message_id}:{row}:{col}:{label}:{size}".encode()
    return hashlib.sha1(raw).hexdigest()[:20]


#----- Drop expired states and keep the registry bounded
def _prune_requests() -> None:
    now = time.time()
    for request_id, request in list(_REQUESTS.items()):
        if now - request.created_at > _REQUEST_TTL:
            _REQUESTS.pop(request_id, None)
    if len(_REQUESTS) > _REQUEST_MAX:
        for request_id in sorted(_REQUESTS, key=lambda rid: _REQUESTS[rid].created_at)[:len(_REQUESTS) - _REQUEST_MAX]:
            _REQUESTS.pop(request_id, None)


#----- Register a candidate for later playback; returns the stable request id
def register(token: str, candidate: Candidate, title: str) -> tuple[str, ExternalRequest]:
    _prune_requests()
    request_id = _make_request_id(
        token, candidate.chat_id, candidate.message_id, candidate.row, candidate.col,
        candidate.label, candidate.size,
    )
    existing = _REQUESTS.get(request_id)
    if existing and time.time() - existing.created_at <= _REQUEST_TTL:
        existing.token = token
        existing.title = title
        return request_id, existing

    request = ExternalRequest(
        request_id=request_id,
        token=token,
        chat_id=candidate.chat_id,
        message_id=candidate.message_id,
        row=candidate.row,
        col=candidate.col,
        label=candidate.label,
        quality=candidate.quality,
        size=candidate.size,
        audio=candidate.audio,
        tamil=candidate.tamil,
        callback_data=candidate.callback_data,
        title=title,
        created_at=time.time(),
    )
    _REQUESTS[request_id] = request
    return request_id, request


#----- Look up a request, optionally checking that it belongs to the token
def get_request(request_id: str, token: Optional[str] = None) -> Optional[ExternalRequest]:
    request = _REQUESTS.get(request_id)
    if not request:
        return None
    if time.time() - request.created_at > _REQUEST_TTL:
        _REQUESTS.pop(request_id, None)
        return None
    if token is not None and request.token != token:
        return None
    return request


#----- Prefetch selected candidates in the background (best effort)
async def prefetch(requests: List[ExternalRequest]) -> None:
    for request in requests:
        try:
            await prepare_request(request)
        except ExternalSearchBusy as exc:
            await asyncio.sleep(min(30, max(2, exc.wait)))
        except Exception as exc:
            LOGGER.warning(f"[MSEARCH] Prefetch failed for {request.label}: {exc}")
