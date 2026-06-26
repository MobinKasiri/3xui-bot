"""Ensure optional bot schema pieces exist (safe to run on every startup)."""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.db.database import Database

logger = logging.getLogger(__name__)


async def ensure_bot_schema(db: Database) -> None:
    """Add columns introduced after first deploy without failing startup."""
    dialect = db.engine.dialect.name
    async with db.engine.begin() as conn:
        if dialect == "postgresql":
            await conn.execute(
                text(
                    "ALTER TABLE transactions "
                    "ADD COLUMN IF NOT EXISTS bot_admin_notify TEXT"
                )
            )
            return

        if dialect == "sqlite":
            rows = await conn.execute(text("PRAGMA table_info(transactions)"))
            cols = {row[1] for row in rows.fetchall()}
            if "bot_admin_notify" not in cols:
                await conn.execute(
                    text("ALTER TABLE transactions ADD COLUMN bot_admin_notify TEXT")
                )
            return

        logger.warning("ensure_bot_schema: unsupported dialect %s", dialect)
