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
    referrer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referred_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    purchase_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_bonus_given: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    friend_bonus_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    friend_welcome_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    referrer: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[referrer_id], back_populates="referrals_sent"
    )

    def __repr__(self) -> str:
        return (
            f"<Referral referrer={self.referrer_id} referred={self.referred_id} "
            f"purchases={self.purchase_count}>"
        )

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
    async def list_for_referrer(cls, session: AsyncSession, referrer_id: int) -> list[Self]:
        result = await session.execute(
            select(cls).where(cls.referrer_id == referrer_id).order_by(cls.created_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def count_for_referrer(cls, session: AsyncSession, referrer_id: int) -> int:
        from sqlalchemy import func as f
        result = await session.execute(
            select(f.count()).select_from(cls).where(cls.referrer_id == referrer_id)
        )
        return result.scalar_one()

    @classmethod
    async def stats_for_referrer(
        cls, session: AsyncSession, referrer_id: int
    ) -> tuple[int, int, int]:
        """Return (referral_count, purchase_count_sum, total_bonus_given_sum)."""
        from sqlalchemy import func as f
        result = await session.execute(
            select(
                f.count(),
                f.coalesce(f.sum(cls.purchase_count), 0),
                f.coalesce(f.sum(cls.total_bonus_given), 0),
            )
            .select_from(cls)
            .where(cls.referrer_id == referrer_id)
        )
        row = result.one()
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)

    @classmethod
    async def mark_friend_bonus(
        cls, session: AsyncSession, ref_id: int, *, welcome_code: str | None = None
    ) -> None:
        values: dict[str, Any] = {"friend_bonus_given": True}
        if welcome_code:
            values["friend_welcome_code"] = welcome_code
        await session.execute(
            update(cls).where(cls.id == ref_id).values(**values)
        )
        await session.commit()

    @classmethod
    async def add_purchase(
        cls, session: AsyncSession, ref_id: int, bonus_added: int
    ) -> None:
        await session.execute(
            update(cls)
            .where(cls.id == ref_id)
            .values(
                purchase_count=cls.purchase_count + 1,
                total_bonus_given=cls.total_bonus_given + bonus_added,
            )
        )
        await session.commit()
