from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Self

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

logger = logging.getLogger(__name__)


class DiscountUsage(Base):
    __tablename__ = "discount_usage"
    __table_args__ = (
        UniqueConstraint("code_id", "user_id", name="uq_discount_usage_code_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("discount_codes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    used_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> Self:
        usage = cls(**kwargs)
        session.add(usage)
        await session.commit()
        await session.refresh(usage)
        return usage

    @classmethod
    async def has_used(cls, session: AsyncSession, code_id: int, user_id: int) -> bool:
        from sqlalchemy import func as f
        result = await session.execute(
            select(f.count())
            .select_from(cls)
            .where(cls.code_id == code_id, cls.user_id == user_id)
        )
        return (result.scalar_one() or 0) > 0

    @classmethod
    async def count_for_code(cls, session: AsyncSession, code_id: int) -> int:
        from sqlalchemy import func as f
        result = await session.execute(
            select(f.count()).select_from(cls).where(cls.code_id == code_id)
        )
        return result.scalar_one()
