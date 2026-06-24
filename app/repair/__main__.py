"""
Minimal repair bot — answers users when the main bot container is down.

Uses the same BOT_TOKEN and webhook URL as the main bot. Nginx forwards
/webhook here on 502/503/504 from the main bot upstream.

Messages come from panel Settings → تعمیر ربات (maintenance.json).
"""
from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from app.repair.message import repair_user_message

TELEGRAM_WEBHOOK = "/webhook"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8091

logger = logging.getLogger(__name__)
router = Router(name="repair")


@router.message(F.text)
async def on_text(message: Message) -> None:
    await message.answer(repair_user_message())


@router.message()
async def on_any(message: Message) -> None:
    await message.answer(repair_user_message())


@router.callback_query()
async def on_callback(callback: CallbackQuery) -> None:
    text = repair_user_message()
    await callback.answer("ربات موقتاً در حال بروزرسانی است.", show_alert=True)
    if callback.message:
        try:
            await callback.message.answer(text)
        except Exception:
            logger.exception("Failed to answer callback for user %s", callback.from_user.id)


async def _run() -> None:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN is required for repair-bot")

    port = int(os.environ.get("REPAIR_PORT", DEFAULT_PORT))

    logging.basicConfig(
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format=os.environ.get(
            "LOG_FORMAT", "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        ),
    )

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    app = web.Application()

    async def health_handler(_request: web.Request) -> web.Response:
        return web.Response(text="OK", status=200)

    app.router.add_get("/health", health_handler)

    webhook_handler = SimpleRequestHandler(dispatcher=dispatcher, bot=bot)
    webhook_handler.register(app, path=TELEGRAM_WEBHOOK)
    setup_application(app, dispatcher, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, DEFAULT_HOST, port)
    await site.start()
    logger.info("Repair bot listening on %s:%s (failover for main bot)", DEFAULT_HOST, port)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Repair bot stopped.")
