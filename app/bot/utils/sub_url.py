"""Subscription URL helpers — standard /s/ vs Clash /clash/ with Iran bypass."""
from __future__ import annotations


def resolve_clash_sub_base(standard_base: str, explicit: str = "") -> str:
    """Derive Clash subscription base from XUI_SUB_CLASH_BASE_URL or /s/ → /clash/."""
    raw = (explicit or "").strip()
    if raw:
        return raw.rstrip("/") + "/"
    base = (standard_base or "").rstrip("/")
    if "/s/" in base:
        return base.replace("/s/", "/clash/", 1) + "/"
    if base.endswith("/s"):
        return base[:-2] + "/clash/"
    return f"{base}/clash/"


def is_clash_subscription_url(url: str) -> bool:
    return "/clash/" in (url or "")
