"""Persist payment receipt images on disk for admin panel (Telegram file_id alone is unreliable)."""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import Message

from app.config import DEFAULT_DATA_DIR

logger = logging.getLogger(__name__)

RECEIPTS_DIR = DEFAULT_DATA_DIR / "receipts"
LOCAL_PREFIX = "local:"


def receipt_file_path(tx_id: int) -> Path:
    return RECEIPTS_DIR / f"{tx_id}.jpg"


def local_receipt_marker(tx_id: int) -> str:
    return f"{LOCAL_PREFIX}{tx_id}"


def is_local_receipt(value: str | None) -> bool:
    return bool(value and value.startswith(LOCAL_PREFIX))


def _image_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    doc = message.document
    if doc and doc.mime_type and doc.mime_type.startswith("image/"):
        return doc.file_id
    return None


def receipt_file_id(message: Message) -> str | None:
    """Telegram file_id for a photo or image document in a message."""
    return _image_file_id(message)


async def download_receipt_by_file_id(bot: Bot, tx_id: int, file_id: str) -> str | None:
    """Download by file_id; returns ``local:{tx_id}`` on success."""
    if not file_id or file_id.startswith(LOCAL_PREFIX):
        path = receipt_file_path(tx_id)
        return local_receipt_marker(tx_id) if path.is_file() and path.stat().st_size > 0 else None

    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = receipt_file_path(tx_id)
    try:
        tg_file = await bot.get_file(file_id)
        if not tg_file.file_path:
            logger.warning("Telegram get_file empty path tx=%s", tx_id)
            return None
        await bot.download_file(tg_file.file_path, destination=dest)
        logger.info("Backfilled receipt tx=%s -> %s", tx_id, dest)
        return local_receipt_marker(tx_id)
    except Exception:
        logger.exception("Failed to backfill receipt tx=%s", tx_id)
        return None


async def persist_receipt_photo(message: Message, tx_id: int) -> str | None:
    """
    Download receipt to ``data/receipts/{tx_id}.jpg``.
    Returns ``local:{tx_id}`` on success, else the Telegram ``file_id`` fallback.
    """
    file_id = _image_file_id(message)
    if not file_id:
        return None

    saved = await download_receipt_by_file_id(message.bot, tx_id, file_id)
    return saved or file_id
