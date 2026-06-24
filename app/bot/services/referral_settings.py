"""Referral program settings — loaded from shared referral.json (panel-editable)."""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_REFERRAL: dict[str, Any] = {
    "referrer_bonus_toman": 50000,
    "friend_welcome": {
        "type": "discount_percent",
        "percent": 20,
        "toman": 0,
        "valid_days": 30,
    },
    "texts": {
        "landing_no_stats": (
            "🤝 <b>دوستت رو دعوت کن، هر دو سود می‌برید!</b>\n\n"
            "هر بار که یه نفر با لینک تو بیاد و سرویس بخره،\n"
            "<b>{ref_bonus}</b> تومان به کیف پولت واریز می‌شه. 💵\n\n"
            "دوستت هم <b>{friend_gift}</b> دریافت می‌کنه\n"
            "تا از همون اول بتونه سرویس بگیره. 🎁\n\n"
            "🔗 <b>لینک دعوت اختصاصی:</b>\n"
            "<code>{ref_link}</code>"
        ),
        "landing_with_stats": (
            "🤝 <b>دعوت دوستان — NC VPN</b>\n\n"
            "با دعوت از دوستان و خرید آن‌ها با لینک شما:\n"
            "💵 <b>{ref_bonus}</b> تومان به کیف پول شما اضافه می‌شود\n"
            "🎁 دوستتان <b>{friend_gift}</b> دریافت می‌کند\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📊 <b>وضعیت شما:</b>\n"
            "👤 تعداد دعوت‌شده‌ها: <b>{count}</b> نفر\n"
            "🛒 مجموع خریدها: <b>{purchases}</b> بار\n"
            "💰 کل پاداش دریافتی: <b>{total_revenue}</b> تومان\n\n"
            "🔗 <b>لینک ویژه شما:</b>\n"
            "<code>{ref_link}</code>"
        ),
        "ready_post": (
            "<b>⚡️ NC VPN — VPN سریع و ایمن</b>\n\n"
            "🌐 پروتکل‌های مدرن VLESS\n"
            "🤝 پشتیبانی آنلاین\n"
            "📲 سازگار با تمامی دستگاه‌ها و اپراتورها\n"
            "🔒 بدون محدودیت تعداد دستگاه\n\n"
            "با استفاده از لینک من عضو شو و {friend_gift} بگیر:\n"
            "{ref_link}"
        ),
        "share_dialog": "⚡️ VPN پرسرعت — NC VPN",
        "friend_welcome": (
            "🎁 <b>هدیه خوش‌آمد NC VPN</b>\n\n"
            "با لینک دعوت دوستت عضو شدی!\n"
            "کد تخفیف اختصاصی تو:\n"
            "<code>{code}</code>\n\n"
            "{friend_gift} — فقط یک‌بار قابل استفاده در خرید."
        ),
    },
    "images": {
        "landing": "",
        "ready_post": "referral_post.jpg",
    },
}


def default_referral_file() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "referral.json"


def resolve_referral_file(data_dir: Path | None = None) -> Path:
    if data_dir is not None:
        return data_dir / "referral.json"
    return default_referral_file()


def _merge_defaults(raw: dict | None) -> dict[str, Any]:
    base = deepcopy(DEFAULT_REFERRAL)
    if not isinstance(raw, dict):
        return base
    if "referrer_bonus_toman" in raw:
        base["referrer_bonus_toman"] = int(raw["referrer_bonus_toman"] or 0)
    fw = raw.get("friend_welcome")
    if isinstance(fw, dict):
        base["friend_welcome"].update(
            {k: fw[k] for k in ("type", "percent", "toman", "valid_days") if k in fw}
        )
    texts = raw.get("texts")
    if isinstance(texts, dict):
        for key, val in texts.items():
            if isinstance(val, str) and val.strip():
                base["texts"][key] = val
    images = raw.get("images")
    if isinstance(images, dict):
        for key, val in images.items():
            if isinstance(val, str):
                base["images"][key] = val
    return base


def load_referral_settings(data_dir: Path | None = None) -> dict[str, Any]:
    path = resolve_referral_file(data_dir)
    if not path.is_file():
        example = path.parent / "referral.example.json"
        if example.is_file():
            try:
                with example.open(encoding="utf-8") as fh:
                    return _merge_defaults(json.load(fh))
            except (OSError, json.JSONDecodeError):
                pass
        return deepcopy(DEFAULT_REFERRAL)
    try:
        with path.open(encoding="utf-8") as fh:
            return _merge_defaults(json.load(fh))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load referral settings from %s: %s", path, exc)
        return deepcopy(DEFAULT_REFERRAL)


def save_referral_settings(data: dict, data_dir: Path | None = None) -> Path:
    path = resolve_referral_file(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = _merge_defaults(data)
    tmp = path.parent / f".{path.name}.tmp"
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        fh.flush()
    tmp.replace(path)
    return path


@dataclass
class ReferralSettingsView:
    data: dict[str, Any] = field(default_factory=lambda: deepcopy(DEFAULT_REFERRAL))
    data_dir: Path | None = None
    _mtime: float = 0.0

    def reload_if_changed(self) -> None:
        path = resolve_referral_file(self.data_dir)
        if not path.is_file():
            return
        try:
            mtime = path.stat().st_mtime
            if mtime == self._mtime and self.data:
                return
            self.data = load_referral_settings(self.data_dir)
            self._mtime = mtime
        except OSError:
            pass

    @property
    def referrer_bonus_toman(self) -> int:
        self.reload_if_changed()
        env_fallback = 0
        return int(self.data.get("referrer_bonus_toman") or env_fallback)

    @property
    def friend_welcome(self) -> dict[str, Any]:
        self.reload_if_changed()
        fw = self.data.get("friend_welcome")
        return fw if isinstance(fw, dict) else DEFAULT_REFERRAL["friend_welcome"]

    def friend_gift_label(self) -> str:
        fw = self.friend_welcome
        kind = (fw.get("type") or "discount_percent").strip()
        if kind == "wallet_toman":
            amount = int(fw.get("toman") or 0)
            if amount <= 0:
                return "هدیه خوش‌آمد"
            return f"{amount:,} تومان اعتبار"
        pct = int(fw.get("percent") or 20)
        return f"کد تخفیف {pct}٪"

    def text(self, key: str, **kwargs: Any) -> str:
        self.reload_if_changed()
        template = (self.data.get("texts") or {}).get(key) or DEFAULT_REFERRAL["texts"].get(key, "")
        try:
            return template.format(**kwargs)
        except KeyError as exc:
            logger.warning("Missing referral template key %s in %s", exc, key)
            return template

    def image_name(self, slot: str) -> str:
        self.reload_if_changed()
        name = (self.data.get("images") or {}).get(slot) or ""
        return (name or "").strip()


def referral_settings_for_config(config) -> ReferralSettingsView:
    data_dir = None
    if config and getattr(config, "pricing", None):
        pf = getattr(config.pricing, "plans_file", None)
        if pf is not None:
            data_dir = Path(pf).parent
    view = ReferralSettingsView(data=load_referral_settings(data_dir), data_dir=data_dir)
    if data_dir:
        path = resolve_referral_file(data_dir)
        if path.is_file():
            try:
                view._mtime = path.stat().st_mtime
            except OSError:
                pass
    return view
