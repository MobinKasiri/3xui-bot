"""Repair gateway messages — panel maintenance.json + optional panel API."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

BUILTIN_DEFAULT_OFFLINE = (
    "⏳ <b>ربات موقتاً در دسترس نیست</b>\n\n"
    "در حال بروزرسانی یا راه‌اندازی مجدد هستیم. لطفاً چند دقیقه دیگر دوباره "
    "<b>/start</b> را بزنید."
)

PRESETS: dict[str, str] = {
    "developing": (
        "🔧 <b>ربات در حال توسعه است</b>\n\n"
        "در حال اضافه کردن قابلیت‌های جدید هستیم. لطفاً کمی بعد دوباره سر بزنید."
    ),
    "updating": (
        "⬆️ <b>بروزرسانی ربات</b>\n\n"
        "نسخه جدید ربات در حال نصب است. به‌زودی با امکانات بهتر برمی‌گردیم."
    ),
    "servers": (
        "🖥 <b>بروزرسانی سرورها</b>\n\n"
        "سرورها در حال ارتقا هستند تا اتصال پایدارتر و سریع‌تری داشته باشید."
    ),
    "bugfix": (
        "🛠 <b>رفع مشکل فنی</b>\n\n"
        "یک مشکل فنی شناسایی شده و در حال رفع آن هستیم. از صبر شما سپاسگزاریم."
    ),
    "maintenance": (
        "⏸ <b>غیرفعال موقت</b>\n\n"
        "ربات به‌صورت موقت غیرفعال شده است. لطفاً بعداً دوباره تلاش کنید."
    ),
}

PANEL_FETCH_TIMEOUT = float(os.environ.get("MAINTENANCE_PANEL_TIMEOUT", "3"))
PANEL_CACHE_SEC = float(os.environ.get("MAINTENANCE_PANEL_CACHE_SEC", "2"))
PANEL_URL = os.environ.get(
    "PANEL_MAINTENANCE_URL",
    "http://nexoranode-panel-api:8000/maintenance/internal",
).strip()
USE_PANEL = os.environ.get("MAINTENANCE_FROM_PANEL", "true").lower() in (
    "1",
    "true",
    "yes",
)

_panel_cache: dict | None = None
_panel_cache_at = 0.0


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def maintenance_file_candidates() -> list[Path]:
    explicit = os.environ.get("MAINTENANCE_FILE", "").strip()
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit))
    plans_file = os.environ.get("PLANS_FILE", "/app/data/plans.json").strip()
    if plans_file:
        paths.append(Path(plans_file).parent / "maintenance.json")
    paths.append(Path("/app/data/maintenance.json"))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _normalize_state(data: dict) -> dict:
    state = {
        "enabled": _as_bool(data.get("enabled")),
        "reason": data.get("reason") or "maintenance",
        "custom_message": data.get("custom_message"),
        "default_offline_message": data.get("default_offline_message"),
        "ends_at": data.get("ends_at"),
    }
    if state["enabled"] and state.get("ends_at"):
        try:
            ends = datetime.fromisoformat(str(state["ends_at"]).replace("Z", "+00:00"))
            if ends.tzinfo:
                ends = ends.replace(tzinfo=None)
            if ends <= datetime.utcnow():
                state["enabled"] = False
        except ValueError:
            pass
    return state


def _load_state_from_file() -> tuple[dict | None, Path | None]:
    for path in maintenance_file_candidates():
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return _normalize_state(data), path
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("maintenance.json unreadable at %s: %s", path, exc)
    return None, None


async def _load_state_from_panel() -> dict | None:
    global _panel_cache, _panel_cache_at
    if not USE_PANEL or not PANEL_URL:
        return None

    now = time.monotonic()
    if _panel_cache is not None and (now - _panel_cache_at) < PANEL_CACHE_SEC:
        return dict(_panel_cache)

    timeout = aiohttp.ClientTimeout(total=PANEL_FETCH_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(PANEL_URL) as resp:
                if resp.status != 200:
                    logger.warning("Panel maintenance API HTTP %s", resp.status)
                    return None
                data = await resp.json()
    except aiohttp.ClientError as exc:
        logger.debug("Panel maintenance API unreachable: %s", exc)
        return None
    except Exception:
        logger.exception("Panel maintenance API failed")
        return None

    if not isinstance(data, dict):
        return None

    state = _normalize_state(data)
    _panel_cache = state
    _panel_cache_at = now
    return state


async def load_state() -> dict:
    """Load maintenance state — panel API first, then local file."""
    panel_state = await _load_state_from_panel()
    if panel_state is not None:
        return panel_state

    file_state, path = _load_state_from_file()
    if file_state is not None:
        return file_state

    if path is None:
        logger.debug(
            "No maintenance.json found (checked: %s)",
            ", ".join(str(p) for p in maintenance_file_candidates()),
        )
    return {"enabled": False, "default_offline_message": None}


def default_offline_message(state: dict | None = None) -> str:
    """Scenario 1: main bot down, planned repair mode OFF."""
    custom = (state or {}).get("default_offline_message")
    if isinstance(custom, str) and custom.strip():
        return custom.strip()
    return BUILTIN_DEFAULT_OFFLINE


def _remaining_persian(ends_at: str | None) -> str | None:
    if not ends_at:
        return None
    try:
        ends = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
        if ends.tzinfo:
            ends = ends.replace(tzinfo=None)
        delta = ends - datetime.utcnow()
        if delta.total_seconds() <= 0:
            return None
        minutes = int(delta.total_seconds() // 60)
        if minutes < 60:
            return f"{minutes} دقیقه"
        hours = minutes // 60
        rem = minutes % 60
        if rem:
            return f"{hours} ساعت و {rem} دقیقه"
        return f"{hours} ساعت"
    except ValueError:
        return None


def planned_repair_message(state: dict | None = None) -> str:
    """Scenario 2: planned repair mode ON (panel enabled)."""
    state = state or {}
    reason = state.get("reason") or "maintenance"
    base = state.get("custom_message") or PRESETS.get(reason, PRESETS["maintenance"])
    remaining = _remaining_persian(state.get("ends_at"))
    if remaining:
        return f"{base}\n\n⏱ زمان تقریبی: <b>{remaining}</b>"
    return base


def is_planned_repair_active(state: dict | None = None) -> bool:
    return _as_bool((state or {}).get("enabled"))


def sync_diagnostics() -> dict:
    file_state, path = _load_state_from_file()
    return {
        "panel_url": PANEL_URL or None,
        "panel_enabled": USE_PANEL,
        "maintenance_file": str(path) if path else None,
        "file_enabled": is_planned_repair_active(file_state) if file_state else False,
        "checked_paths": [str(p) for p in maintenance_file_candidates()],
    }
