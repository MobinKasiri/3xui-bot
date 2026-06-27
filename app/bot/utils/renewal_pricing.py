"""Renewal pricing — automatic discount on extend-existing-sub flows."""
from __future__ import annotations

from dataclasses import dataclass

RENEWAL_DISCOUNT_PERCENT = 10


@dataclass(frozen=True)
class RenewalQuote:
    base_amount: int
    renewal_discount: int
    final_amount: int


def renewal_quote(plan_price: int) -> RenewalQuote:
    """Apply the default renewal discount to a plan list price (Toman)."""
    base = max(0, int(plan_price))
    discount = base * RENEWAL_DISCOUNT_PERCENT // 100
    final = max(0, base - discount)
    return RenewalQuote(base_amount=base, renewal_discount=discount, final_amount=final)
