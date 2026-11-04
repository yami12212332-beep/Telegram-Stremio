"""Subscription-group membership checks shared by /stream and /ms/resolve."""

from __future__ import annotations

import time

from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant

from Backend.helper.settings_manager import SettingsManager
from Backend.logger import LOGGER
from Backend.pyrofork.bot import StreamBot

_membership_cache: dict = {}
_MEMBERSHIP_TTL = 60
_MEMBERSHIP_CACHE_MAX = 5000


def invalidate_membership_cache(user_id: int | None = None) -> None:
    if user_id is None:
        _membership_cache.clear()
        return
    for key in [k for k in _membership_cache if k[1] == user_id]:
        _membership_cache.pop(key, None)


async def is_subscription_member(user_id: int) -> bool:
    group_id = SettingsManager.current().subscription_group_id
    if not group_id:
        return True

    cache_key = (group_id, user_id)
    cached = _membership_cache.get(cache_key)
    now_ts = time.monotonic()
    if cached and (now_ts - cached[0]) < _MEMBERSHIP_TTL:
        return cached[1]

    try:
        member = await StreamBot.get_chat_member(group_id, user_id)
        result = member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
    except UserNotParticipant:
        result = False
    except Exception as exc:
        LOGGER.warning(f"[SUBSCRIPTION] Membership check failed for user {user_id}: {exc}")
        return True

    if len(_membership_cache) >= _MEMBERSHIP_CACHE_MAX:
        for key in [k for k, v in _membership_cache.items() if (now_ts - v[0]) >= _MEMBERSHIP_TTL]:
            _membership_cache.pop(key, None)
        if len(_membership_cache) >= _MEMBERSHIP_CACHE_MAX:
            _membership_cache.clear()

    _membership_cache[cache_key] = (now_ts, result)
    return result
