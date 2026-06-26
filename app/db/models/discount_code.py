from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Self

from sqlalchemy import (
    BigInteger,
    Boolean,
    Integer,
    String,
    func,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

logger = logging.getLogger(__name__)


class DiscountCode(Base):
    __tablename__ = "discount_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)  # flat Toman
    max_uses: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_uses_per_user: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<DiscountCode {self.code} pct={self.discount_percent} amt={self.discount_amount}>"

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> Self:
        code = cls(**kwargs)
        session.add(code)
        await session.commit()
        await session.refresh(code)
        return code

    @classmethod
    async def get_by_code(cls, session: AsyncSession, code: str) -> Self | None:
        result = await session.execute(
            select(cls).where(func.lower(cls.code) == code.lower())
        )
        return result.scalar_one_or_none()

    @classmethod
    async def list_active(cls, session: AsyncSession) -> list[Self]:
        result = await session.execute(
            select(cls).where(cls.is_active == True).order_by(cls.created_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def deactivate(cls, session: AsyncSession, code_id: int) -> bool:
        result = await session.execute(
            update(cls).where(cls.id == code_id).values(is_active=False)
        )
        await session.commit()
        return result.rowcount > 0

    @classmethod
    async def bump_used(cls, session: AsyncSession, code_id: int) -> bool:
        result = await session.execute(
            update(cls).where(cls.id == code_id).values(used_count=cls.used_count + 1)
        )
        await session.commit()
        return result.rowcount > 0
