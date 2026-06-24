"""Forward webhooks to main bot or deliver repair messages."""
from __future__ import annotations

import json
import logging
import os

import aiohttp
from aiogram import Bot

from app.repair.message import (
    default_offline_message,
    is_planned_repair_active,
    load_state,
    planned_repair_message,
)
from app.repair.targets import extract_reply_targets

logger = logging.getLogger(__name__)

MAIN_BOT_WEBHOOK_URL = os.environ.get(
    "MAIN_BOT_WEBHOOK_URL", "http://bot:8090/webhook"
)
FORWARD_TIMEOUT_SEC = float(os.environ.get("REPAIR_FORWARD_TIMEOUT", "25"))


async def forward_to_main_bot(body: bytes, request_headers) -> tuple[int, bytes]:
    headers = {"Content-Type": "application/json"}
    secret = request_headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret

    timeout = aiohttp.ClientTimeout(total=FORWARD_TIMEOUT_SEC)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(MAIN_BOT_WEBHOOK_URL, data=body, headers=headers) as resp:
            return resp.status, await resp.read()


async def deliver_repair_reply(bot: Bot, body: bytes, text: str) -> bool:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Repair gateway: invalid JSON body")
        return False

    if not isinstance(data, dict):
        logger.warning("Repair gateway: webhook body is not an object")
        return False

    chat_id, callback_id = extract_reply_targets(data)

    if callback_id:
        try:
            await bot.answer_callback_query(
                callback_id,
                "ربات موقتاً در دسترس نیست.",
                show_alert=True,
            )
        except Exception:
            logger.debug("Could not answer callback %s", callback_id)

    if chat_id is None:
        update_id = data.get("update_id")
        logger.info(
            "Repair gateway: no user chat in update_id=%s — skip Telegram reply",
            update_id,
        )
        return False

    try:
        await bot.send_message(chat_id, text)
        logger.info("Repair gateway: sent message to chat %s", chat_id)
        return True
    except Exception:
        logger.exception("Repair gateway: failed to send message to chat %s", chat_id)
        return False


async def handle_webhook(bot: Bot, body: bytes, request_headers) -> tuple[int, bytes]:
    state = await load_state()
    planned = is_planned_repair_active(state)

    if planned:
        text = planned_repair_message(state)
        logger.info("Planned repair active — replying to user")
        await deliver_repair_reply(bot, body, text)
        return 200, b"{}"

    try:
        status, resp_body = await forward_to_main_bot(body, request_headers)
        if status == 200:
            return status, resp_body
        logger.warning(
            "Main bot returned HTTP %s — using default offline message", status
        )
    except aiohttp.ClientError as exc:
        logger.warning(
            "Main bot unreachable (%s) — using default offline message", exc
        )
    except Exception:
        logger.exception("Main bot forward failed — using default offline message")

    text = default_offline_message(state)
    sent = await deliver_repair_reply(bot, body, text)
    if not sent:
        logger.warning("Repair gateway: offline message was not delivered")
    return 200, b"{}"
