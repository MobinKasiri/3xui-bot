"""Extract chat/callback targets from raw Telegram webhook JSON."""
from __future__ import annotations

from typing import Any


def _chat_id_from_message(msg: dict[str, Any] | None) -> int | None:
    if not isinstance(msg, dict):
        return None
    chat = msg.get("chat")
    if isinstance(chat, dict) and isinstance(chat.get("id"), int):
        return chat["id"]
    return None


def extract_reply_targets(data: dict[str, Any]) -> tuple[int | None, str | None]:
    """Return (chat_id, callback_query_id) for user-visible replies."""
    callback_id: str | None = None
    chat_id: int | None = None

    for key in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "business_message",
        "edited_business_message",
    ):
        if chat_id is None:
            chat_id = _chat_id_from_message(data.get(key))

    cb = data.get("callback_query")
    if isinstance(cb, dict):
        callback_id = cb.get("id")
        if chat_id is None:
            chat_id = _chat_id_from_message(cb.get("message"))

    if chat_id is None:
        shipping = data.get("shipping_query")
        if isinstance(shipping, dict):
            user = shipping.get("from")
            if isinstance(user, dict) and isinstance(user.get("id"), int):
                chat_id = user["id"]

        pre_checkout = data.get("pre_checkout_query")
        if isinstance(pre_checkout, dict):
            user = pre_checkout.get("from")
            if isinstance(user, dict) and isinstance(user.get("id"), int):
                chat_id = user["id"]

    return chat_id, callback_id
