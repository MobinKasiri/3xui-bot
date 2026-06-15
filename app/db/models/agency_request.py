from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Self

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


class AgencyRequest(Base):
    __tablename__ = "agency_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_PENDING)
    admin_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<AgencyRequest id={self.id} user={self.user_id} status={self.status}>"

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> Self:
        req = cls(**kwargs)
        session.add(req)
        await session.commit()
        await session.refresh(req)
        return req

    @classmethod
    async def get(cls, session: AsyncSession, req_id: int) -> Self | None:
        result = await session.execute(select(cls).where(cls.id == req_id))
        return result.scalar_one_or_none()

    @classmethod
    async def get_pending(cls, session: AsyncSession) -> list[Self]:
        result = await session.execute(
            select(cls).where(cls.status == STATUS_PENDING).order_by(cls.created_at.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def count_pending(cls, session: AsyncSession) -> int:
        from sqlalchemy import func as f
        result = await session.execute(
            select(f.count()).select_from(cls).where(cls.status == STATUS_PENDING)
        )
        return result.scalar_one()

    @classmethod
    async def update_status(cls, session: AsyncSession, req_id: int, status: str, response: str | None = None) -> None:
        await session.execute(
            update(cls).where(cls.id == req_id).values(status=status, admin_response=response)
        )
        await session.commit()
