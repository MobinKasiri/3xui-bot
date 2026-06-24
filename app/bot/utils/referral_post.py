"""Resolve referral post / landing images."""
from __future__ import annotations

from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_FALLBACK_NAMES = ("referral_post.jpg", "referral_post.png", "referral_post.webp")


def resolve_referral_image(
    configured_name: str | None = None,
    *,
    data_dir: Path | None = None,
    explicit: Path | None = None,
) -> Path | None:
    """First existing file wins: env path → configured name in data dir → bundled assets."""
    if explicit is not None:
        path = explicit.expanduser()
        if path.is_file():
            return path

    candidates: list[str] = []
    if configured_name:
        candidates.append(configured_name.strip())
    candidates.extend(_FALLBACK_NAMES)

    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        if data_dir is not None:
            path = data_dir / name
            if path.is_file():
                return path
        path = _ASSETS_DIR / name
        if path.is_file():
            return path
    return None


def resolve_referral_post_image(
    explicit: Path | None = None,
    *,
    data_dir: Path | None = None,
) -> Path | None:
    """Backward-compatible helper for ready-post image."""
    return resolve_referral_image(None, data_dir=data_dir, explicit=explicit)
