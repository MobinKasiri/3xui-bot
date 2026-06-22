"""Telegram custom emoji helpers — vector icons only, no colorful Unicode fallbacks."""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_I18N = Path(__file__).resolve().parent.parent / "i18n"
REGISTRY_PATH = _I18N / "emoji_registry.json"
IDS_PATH = _I18N / "emoji_ids.json"

# Plain-text markers when vector emoji IDs are not synced (no colorful Telegram emoji).
_GLYPHS: dict[str, str] = {
    "confirm": "✓",
    "error": "✗",
    "reject": "✗",
    "cancel": "✗",
    "close": "✗",
    "warning": "!",
    "pending": "…",
    "ban": "×",
    "info": "i",
}


def _enabled() -> bool:
    raw = os.environ.get("USE_CUSTOM_EMOJI", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


@lru_cache(maxsize=1)
def _registry() -> dict[str, dict]:
    if not REGISTRY_PATH.is_file():
        return {}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _pack_ids() -> dict[str, list[dict]]:
    if not IDS_PATH.is_file():
        return {}
    try:
        return json.loads(IDS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Invalid emoji_ids.json — run scripts/sync_emoji_packs.py")
        return {}


def reload_emoji_cache() -> None:
    _registry.cache_clear()
    _pack_ids.cache_clear()


def count_loaded() -> tuple[int, int]:
    packs = _pack_ids()
    return sum(len(v) for v in packs.values()), len(packs)


def icon_id(key: str) -> str | None:
    if not _enabled():
        return None
    spec = _registry().get(key)
    if not spec or key.startswith("_"):
        return None
    pack = spec.get("pack", "")
    index = int(spec.get("index", -1))
    rows = _pack_ids().get(pack, [])
    if index < 0 or index >= len(rows):
        return None
    eid = rows[index].get("id") or ""
    return eid or None


def i(key: str) -> str:
    """Custom vector emoji HTML, or a minimal plain glyph — never colorful Unicode emoji."""
    eid = icon_id(key)
    if eid:
        spec = _registry().get(key, {})
        alt = str(spec.get("alt", "·"))
        return f'<tg-emoji emoji-id="{eid}">{alt}</tg-emoji>'
    return _GLYPHS.get(key, "")


def p(key: str) -> str:
    """Like i() but adds a trailing space when non-empty (for message prefixes)."""
    s = i(key)
    return f"{s} " if s else ""


def btn_label(key: str | None, text: str) -> str:
    """Button caption: vector icon via API when synced; otherwise clean text only."""
    return text.strip()


class _Emoji:
    def __getattr__(self, name: str) -> str:
        if name.startswith("_"):
            raise AttributeError(name)
        return i(name)


E = _Emoji()
