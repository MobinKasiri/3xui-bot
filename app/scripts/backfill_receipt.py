#!/usr/bin/env python3
"""Backfill receipt images from Telegram file_id to data/receipts/{tx_id}.jpg."""
from __future__ import annotations

import asyncio
import sys

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.bot.utils.receipt_storage import download_receipt_by_file_id, is_local_receipt
from app.config import load_config
from app.db.models import Transaction


async def backfill_one(session: AsyncSession, bot: Bot, tx_id: int) -> bool:
    tx = await Transaction.get(session, tx_id)
    if not tx or not tx.payment_receipt:
        print(f"tx {tx_id}: no payment_receipt")
        return False

    ref = tx.payment_receipt
    file_id = ref
    if is_local_receipt(ref):
        file_id = None
        from app.bot.utils.receipt_storage import receipt_file_path

        if receipt_file_path(tx_id).is_file():
            print(f"tx {tx_id}: already on disk")
            return True

    if not file_id:
        print(f"tx {tx_id}: local marker but file missing and no file_id")
        return False

    marker = await download_receipt_by_file_id(bot, tx_id, file_id)
    if not marker:
        print(f"tx {tx_id}: Telegram download failed")
        return False

    await Transaction.update(session, tx_id, payment_receipt=marker)
    print(f"tx {tx_id}: saved -> {marker}")
    return True


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: backfill_receipt.py <tx_id> [tx_id ...]")
        sys.exit(1)

    tx_ids = [int(x) for x in sys.argv[1:]]
    config = load_config()
    bot = Bot(token=config.bot.TOKEN)
    engine = create_async_engine(config.database.URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    ok = 0
    async with session_factory() as session:
        for tx_id in tx_ids:
            if await backfill_one(session, bot, tx_id):
                ok += 1
        await session.commit()

    await bot.session.close()
    await engine.dispose()
    print(f"Done: {ok}/{len(tx_ids)} succeeded")


if __name__ == "__main__":
    asyncio.run(main())
