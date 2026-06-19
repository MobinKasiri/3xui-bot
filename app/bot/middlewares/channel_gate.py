"""Block bot usage until the user joins required channels."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.i18n import fa
from app.bot.services.required_channels import channel_gate_keyboard
from app.config import Config
from app.db.models import User

logger = logging.getLogger(__name__)


class ChannelGateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        config: Config | None = data.get("config")
        user: User | None = data.get("user")
        bot = data.get("bot")

        if (
            not config
            or not config.bot.REQUIRED_CHANNELS
            or user is None
            or bot is None
        ):
            return await handler(event, data)

        if user.tg_id in config.bot.ADMINS:
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == "channel:joined":
            return await handler(event, data)

        from app.bot.services.required_channels import user_joined_all

        if await user_joined_all(bot, user.tg_id, config.bot.REQUIRED_CHANNELS):
            return await handler(event, data)

        markup = channel_gate_keyboard(config.bot.REQUIRED_CHANNELS)
        try:
            if isinstance(event, Message):
                await event.answer(fa.CHANNEL_GATE_TEXT, reply_markup=markup)
            elif isinstance(event, CallbackQuery):
                await event.message.edit_text(fa.CHANNEL_GATE_TEXT, reply_markup=markup)
                await event.answer()
        except Exception:
            logger.exception("Failed to show channel gate for user %s", user.tg_id)
        return None
