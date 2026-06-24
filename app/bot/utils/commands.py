import logging

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats

from app.bot.i18n import fa
from app.bot.utils.emoji import plain_alert_text

logger = logging.getLogger(__name__)


def _truncate(text: str, limit: int) -> str:
    text = plain_alert_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def setup(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description=fa.CMD_START),
        BotCommand(command="buy", description=fa.CMD_BUY),
        BotCommand(command="configs", description=fa.CMD_CONFIGS),
        BotCommand(command="topup", description=fa.CMD_TOPUP),
    ]

    await bot.set_my_commands(
        commands=commands,
        scope=BotCommandScopeAllPrivateChats(),
    )
    logger.info("Bot commands configured successfully.")

    try:
        await bot.set_my_description(description=_truncate(fa.BOT_DESCRIPTION, 512))
        await bot.set_my_short_description(
            short_description=_truncate(fa.BOT_SHORT_DESCRIPTION, 120)
        )
        logger.info("Bot profile description updated.")
    except Exception as exc:
        logger.warning("Could not update bot description: %s", exc)


async def delete(bot: Bot) -> None:
    await bot.delete_my_commands(
        scope=BotCommandScopeAllPrivateChats(),
    )
    logger.info("Bot commands removed successfully.")
