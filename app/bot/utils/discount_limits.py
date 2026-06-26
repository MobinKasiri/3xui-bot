"""Shared discount limit helpers (0 = unlimited)."""


def is_unlimited(limit: int | None) -> bool:
    return limit is None or limit <= 0


def is_overall_exhausted(used_count: int, max_uses: int) -> bool:
    if is_unlimited(max_uses):
        return False
    return used_count >= max_uses


def is_user_exhausted(user_uses: int, max_uses_per_user: int) -> bool:
    if is_unlimited(max_uses_per_user):
        return False
    return user_uses >= max_uses_per_user
