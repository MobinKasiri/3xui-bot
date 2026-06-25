"""Subscription URL helpers — standard /s/ (profile page) with Iran routing bypass."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_ROUTING_RULES = """GEOSITE,category-ir,DIRECT
GEOIP,ir,DIRECT
GEOIP,private,DIRECT
MATCH,PROXY"""

# Backward-compatible alias (Clash format uses the same rule set).
DEFAULT_CLASH_RULES = DEFAULT_ROUTING_RULES


def resolve_standard_sub_base(standard_base: str) -> str:
    return (standard_base or "").rstrip("/") + "/"


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
    if is_clash_subscription_url(normalized):
        return normalized
    std = resolve_standard_sub_base(standard_base)
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


def normalize_to_standard_url(url: str, standard_base: str = "") -> str:
    """Convert stored /clash/ links back to /s/ for user-facing copy/import."""
    if not url:
        return url
    if "/clash/" in url:
        return url.replace("/clash/", "/s/", 1)
    if standard_base and not url.startswith("http"):
        return resolve_standard_sub_base(standard_base) + url.lstrip("/")
    return url


def build_subscription_url(
    sub_id: str,
    standard_base: str,
    clash_base: str = "",
    *,
    use_clash: bool = False,
) -> str:
    """Build a public subscription URL for the given sub id."""
    if use_clash:
        base = resolve_clash_sub_base(standard_base, clash_base)
    else:
        base = resolve_standard_sub_base(standard_base)
    return base + sub_id
