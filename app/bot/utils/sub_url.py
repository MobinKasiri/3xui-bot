"""Subscription URL helpers — standard /s/ vs Clash /clash/ with Iran bypass."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_CLASH_RULES = """GEOSITE,category-ir,DIRECT
GEOIP,ir,DIRECT
GEOIP,private,DIRECT
MATCH,PROXY"""


def _derive_clash_base(standard_base: str) -> str:
    base = (standard_base or "").rstrip("/")
    if "/s/" in base:
        return base.replace("/s/", "/clash/", 1) + "/"
    if base.endswith("/s"):
        return base[:-2] + "/clash/"
    return f"{base}/clash/"


def resolve_clash_sub_base(standard_base: str, explicit: str = "") -> str:
    """Derive Clash subscription base from XUI_SUB_CLASH_BASE_URL or /s/ → /clash/."""
    derived = _derive_clash_base(standard_base)
    raw = (explicit or "").strip()
    if not raw:
        return derived
    normalized = raw.rstrip("/") + "/"
    # Misconfigured .env: XUI_SUB_CLASH_BASE_URL copied from XUI_SUB_BASE_URL (/s/).
    if is_clash_subscription_url(normalized):
        return normalized
    std = (standard_base or "").rstrip("/") + "/"
    if normalized == std:
        logger.warning(
            "XUI_SUB_CLASH_BASE_URL points at /s/ — using derived clash base %s",
            derived,
        )
        return derived
    logger.warning(
        "XUI_SUB_CLASH_BASE_URL %s has no /clash/ — using derived clash base %s",
        normalized,
        derived,
    )
    return derived


def is_clash_subscription_url(url: str) -> bool:
    return "/clash/" in (url or "")


def build_subscription_url(
    sub_id: str,
    standard_base: str,
    clash_base: str = "",
    *,
    use_clash: bool = True,
) -> str:
    """Build a public subscription URL for the given sub id."""
    base = resolve_clash_sub_base(standard_base, clash_base) if use_clash else (standard_base or "").rstrip("/") + "/"
    return base + sub_id
