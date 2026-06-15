from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Self

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

logger = logging.getLogger(__name__)


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), nullable=False, index=True)
    referred_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    bonus_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bonus_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    referrer: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[referrer_id], back_populates="referrals_sent"
    )

    def __repr__(self) -> str:
        return f"<Referral referrer={self.referrer_id} referred={self.referred_id}>"

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> Self:
        ref = cls(**kwargs)
        session.add(ref)
        await session.commit()
        await session.refresh(ref)
        return ref

    @classmethod
    async def get_by_referred(cls, session: AsyncSession, referred_id: int) -> Self | None:
        result = await session.execute(select(cls).where(cls.referred_id == referred_id))
        return result.scalar_one_or_none()

    @classmethod
    async def count_for_referrer(cls, session: AsyncSession, referrer_id: int) -> int:
        from sqlalchemy import func as f
        result = await session.execute(
            select(f.count()).select_from(cls).where(cls.referrer_id == referrer_id)
        )
        return result.scalar_one()

    @classmethod
    async def get_pending_bonus(cls, session: AsyncSession, referred_id: int) -> Self | None:
        result = await session.execute(
            select(cls).where(cls.referred_id == referred_id, cls.bonus_given == False)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def mark_bonus_given(cls, session: AsyncSession, ref_id: int, bonus_mb: int) -> None:
        await session.execute(
            update(cls).where(cls.id == ref_id).values(bonus_given=True, bonus_mb=bonus_mb)
        )
        await session.commit()
