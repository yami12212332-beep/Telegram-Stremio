"""Remove staging-channel files that no library entry references.

The M Searcher bridge copies files into a staging channel and the receiver
indexes them. Replace mode and failed/aborted copies can leave messages behind.
This sweep deletes only messages that are older than a safety window and are
not referenced by any movie/tv document in any storage database.
"""

from __future__ import annotations

import time

from Backend.helper.encrypt import decode_string
from Backend.logger import LOGGER


async def _referenced_message_ids(db, staging_bare: str) -> set[int]:
    referenced: set[int] = set()

    for key, database in db.dbs.items():
        if not key.startswith("storage_"):
            continue
        for collection_name in ("movie", "tv"):
            try:
                cursor = database[collection_name].find(
                    {}, {"telegram": 1, "seasons.episodes.telegram": 1}
                )
            except Exception:
                continue

            async for doc in cursor:
                entries = list(doc.get("telegram") or [])
                for season in doc.get("seasons") or []:
                    for episode in season.get("episodes") or []:
                        entries.extend(episode.get("telegram") or [])

                for entry in entries:
                    encoded_ids = []
                    if entry.get("id"):
                        encoded_ids.append(entry["id"])
                    for part in entry.get("parts") or []:
                        if part.get("id"):
                            encoded_ids.append(part["id"])
                        elif part.get("chat_id") is not None and part.get("msg_id") is not None:
                            if str(part["chat_id"]) == staging_bare:
                                referenced.add(int(part["msg_id"]))

                    for encoded in encoded_ids:
                        try:
                            decoded = await decode_string(encoded)
                        except Exception:
                            continue
                        if not isinstance(decoded, dict):
                            continue
                        try:
                            if str(decoded.get("chat_id")) == staging_bare:
                                referenced.add(int(decoded["msg_id"]))
                        except (KeyError, TypeError, ValueError):
                            continue

    return referenced


async def cleanup_orphans(db, client, staging_channel: str, *,
                          min_age_seconds: int = 3600,
                          limit: int = 500) -> int:
    """Delete unreferenced staging messages. Returns the number deleted."""
    try:
        staging = int(staging_channel)
    except (TypeError, ValueError):
        return 0

    bare = str(staging).replace("-100", "")
    referenced = await _referenced_message_ids(db, bare)
    cutoff = time.time() - max(60, int(min_age_seconds))
    deleted = 0
    scanned = 0

    try:
        async for message in client.get_chat_history(staging, limit=limit):
            scanned += 1
            if message.id in referenced:
                continue
            try:
                if message.date and message.date.timestamp() > cutoff:
                    continue
            except Exception:
                pass
            try:
                await client.delete_messages(staging, message.id)
                deleted += 1
            except Exception as exc:
                LOGGER.warning(f"[MSEARCH] staging cleanup could not delete {message.id}: {exc}")
    except Exception as exc:
        LOGGER.warning(f"[MSEARCH] staging cleanup failed: {exc}")

    LOGGER.info(
        f"[MSEARCH] staging cleanup: scanned {scanned}, referenced {len(referenced)}, "
        f"deleted {deleted}"
    )
    return deleted
