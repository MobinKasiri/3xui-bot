from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import User

logger = logging.getLogger(__name__)


class DBSessionMiddleware(BaseMiddleware):
    def __init__(self, session: async_sessionmaker) -> None:
        self.session = session
        logger.debug("Database Session Middleware initialized.")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session() as session:
            tg_user: TelegramUser | None = event.event.from_user

            if tg_user is not None and not tg_user.is_bot:
                user = await User.get(session=session, tg_id=tg_user.id)
                is_new_user = False

                if not user:
                    is_new_user = True
                    user = await User.create(
                        session=session,
                        tg_id=tg_user.id,
                        full_name=tg_user.full_name or tg_user.first_name or "",
                        username=tg_user.username,
                    )
                    logger.info(f"New user {tg_user.id} created.")

                if user.is_banned:
                    from app.bot.i18n.fa import ERRORS
                    try:
                        await event.event.answer(ERRORS["banned"])
                    except Exception:
                        pass
                    return None

                data["user"] = user
                data["session"] = session
                data["is_new_user"] = is_new_user
            else:
                data["session"] = session

            return await handler(event, data)
