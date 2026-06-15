from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Self

from sqlalchemy import BigInteger, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

logger = logging.getLogger(__name__)

# notification types
NOTIF_EXPIRY = "expiry"
NOTIF_TRAFFIC = "traffic"


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    config_id: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    bucket: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2024-01-15" or "80pct"
    sent_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<NotificationLog config={self.config_id} type={self.type} bucket={self.bucket}>"

    @classmethod
    async def already_sent(cls, session: AsyncSession, config_id: int, type: str, bucket: str) -> bool:
        result = await session.execute(
            select(cls).where(
                cls.config_id == config_id,
                cls.type == type,
                cls.bucket == bucket,
            )
        )
        return result.scalar_one_or_none() is not None

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> Self:
        entry = cls(**kwargs)
        session.add(entry)
        await session.commit()
        return entry
