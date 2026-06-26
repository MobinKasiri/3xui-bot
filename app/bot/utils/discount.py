"""Discount-code validation and application."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DiscountCode, DiscountUsage
from app.bot.utils.discount_limits import is_overall_exhausted, is_user_exhausted


@dataclass
class DiscountResult:
    code: DiscountCode | None
    error: str | None  # i18n error key
    discount_amount: int
    final_amount: int


async def validate_and_apply(
    session: AsyncSession,
    code_str: str,
    user_id: int,
    base_amount: int,
) -> DiscountResult:
    """
    Lookup the code, validate, and return the resulting amount.
    On failure, `code` is None and `error` is set to an i18n key inside `fa.ERRORS`.
    NOTE: This function does NOT mark the code as used — call `record_usage()` after the
    purchase actually succeeds.
    """
    if not code_str or not code_str.strip():
        return DiscountResult(None, "invalid_discount", 0, base_amount)

    code = await DiscountCode.get_by_code(session, code_str.strip())
    if code is None or not code.is_active:
        return DiscountResult(None, "invalid_discount", 0, base_amount)

    if code.expires_at and code.expires_at < datetime.utcnow():
        return DiscountResult(None, "invalid_discount", 0, base_amount)

    if is_overall_exhausted(code.used_count, code.max_uses):
        return DiscountResult(None, "invalid_discount", 0, base_amount)

    user_uses = await DiscountUsage.count_for_user(session, code.id, user_id)
    per_user_limit = getattr(code, "max_uses_per_user", 1)
    if is_user_exhausted(user_uses, per_user_limit):
        return DiscountResult(None, "discount_used", 0, base_amount)

    discount_amount = 0
    if code.discount_percent:
        discount_amount = base_amount * code.discount_percent // 100
    elif code.discount_amount:
        discount_amount = min(code.discount_amount, base_amount)
    final = max(0, base_amount - discount_amount)
    return DiscountResult(code, None, discount_amount, final)


async def record_usage(
    session: AsyncSession, code_id: int, user_id: int
) -> None:
    """Insert a discount_usage row and bump the code's used_count."""
    await DiscountUsage.create(session, code_id=code_id, user_id=user_id)
    await DiscountCode.bump_used(session, code_id)
