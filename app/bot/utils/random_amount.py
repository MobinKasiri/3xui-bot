"""Add a random 3-digit suffix to a card-payment amount so the admin can match the receipt."""
from __future__ import annotations

import random

SUFFIX_MIN = 100
SUFFIX_MAX = 999


def add_payment_suffix(base_amount: int) -> int:
    """Return `base_amount + random(SUFFIX_MIN..SUFFIX_MAX)` (inclusive)."""
    if base_amount <= 0:
        return base_amount
    return base_amount + random.randint(SUFFIX_MIN, SUFFIX_MAX)
