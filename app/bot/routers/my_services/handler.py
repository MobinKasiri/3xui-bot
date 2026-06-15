from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import fa
from app.bot.services.xui_api import XUIApiService, XUIError
from app.bot.utils.jalali import to_jalali, days_until
from app.bot.utils.keyboards import back_to_menu_keyboard
from app.bot.utils.persian import to_persian_digits
from app.bot.utils.progress import traffic_bar, format_gb
from app.db.models import User, VPNConfig

logger = logging.getLogger(__name__)
router = Router(name="my_services")


def _service_card_text(
    index: int,
    config: VPNConfig,
    used_bytes: int,
    plans: dict,
) -> str:
    plan = plans.get(config.plan_key, {})
    plan_name = plan.get("name", config.plan_key or "سرویس")

    is_active = config.is_active
    badge = fa.SERVICE_ACTIVE_BADGE if is_active else fa.SERVICE_EXPIRED_BADGE

    now = datetime.now(tz=timezone.utc)
    expiry = config.expiry_date
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    expired = expiry is None or expiry < now

    if expired or not is_active:
        expiry_str = to_jalali(expiry) if expiry else "—"
        return fa.SERVICE_EXPIRED_CARD.format(
            badge=badge,
            index=to_persian_digits(index),
            plan_name=plan_name,
            expiry_jalali=expiry_str,
        )

    bar = traffic_bar(used_bytes, config.traffic_limit_bytes, width=10)
    used_gb = used_bytes / (1024 ** 3)
    total_gb = config.traffic_limit_bytes / (1024 ** 3)
    pct = (used_bytes / config.traffic_limit_bytes * 100) if config.traffic_limit_bytes else 0
    expiry_str = to_jalali(expiry) if expiry else "—"
    days_left = days_until(expiry) if expiry else 0
    days_str = fa.DAYS_LEFT_FMT.format(n=to_persian_digits(days_left)) if days_left > 0 else fa.DAYS_EXPIRED

    return fa.SERVICE_CARD.format(
        badge=badge,
        index=to_persian_digits(index),
        plan_name=plan_name,
        bar=bar,
        used_gb=used_gb,
        total_gb=total_gb,
        pct=pct,
        expiry_jalali=expiry_str,
        days_left=days_str,
    )


async def _render_services(target, user: User, session: AsyncSession, **kwargs) -> None:
    """Shared helper — works for both Message and CallbackQuery targets."""
    from aiogram.types import Message as Msg, CallbackQuery as CQ

    configs = await VPNConfig.get_for_user(session, user.tg_id)
    active_configs = [c for c in configs if c.is_active]

    config_obj = kwargs.get("config")
    plans = config_obj.pricing.PLANS if config_obj else {}
    xui: XUIApiService | None = kwargs.get("xui_service")

    if not active_configs:
        builder = InlineKeyboardBuilder()
        builder.button(text=fa.MAIN_MENU_BUTTONS["purchase"], callback_data="purchase:start")
        builder.adjust(1)
        markup = builder.as_markup()
        if isinstance(target, Msg):
            await target.answer(fa.MY_SERVICES_EMPTY, reply_markup=markup)
        else:
            await target.message.edit_text(fa.MY_SERVICES_EMPTY, reply_markup=markup)
            await target.answer()
        return

    text_parts = [fa.MY_SERVICES_HEADER]
    builder = InlineKeyboardBuilder()

    for i, config in enumerate(active_configs, start=1):
        used_bytes = config.traffic_used_bytes
        if xui:
            try:
                traffic = await xui.get_client_traffic(config.panel_email)
                used_bytes = traffic.used_bytes
            except XUIError:
                pass

        text_parts.append(_service_card_text(i, config, used_bytes, plans))
        builder.button(
            text=f"🔗 لینک سرویس {to_persian_digits(i)}",
            callback_data=f"my_services:link:{config.id}",
        )
        builder.button(
            text=f"🔄 تمدید {to_persian_digits(i)}",
            callback_data=f"renewal:config:{config.id}",
        )

    builder.button(text=fa.REFRESH, callback_data="my_services:list")
    builder.adjust(*([2] * len(active_configs)), 1)

    full_text = fa.SERVICE_SEPARATOR.join(text_parts)
    markup = builder.as_markup()
    if isinstance(target, Msg):
        await target.answer(full_text, reply_markup=markup)
    else:
        await target.message.edit_text(full_text, reply_markup=markup)
        await target.answer()


@router.callback_query(F.data == "my_services:list")
async def cb_my_services(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    **kwargs,
) -> None:
    await _render_services(callback, user, session, **kwargs)


@router.callback_query(F.data.startswith("my_services:link:"))
async def cb_get_link(
    callback: CallbackQuery,
    session: AsyncSession,
    **kwargs,
) -> None:
    config_id = int(callback.data.split(":")[-1])
    config = await VPNConfig.get(session, config_id)
    if not config:
        await callback.answer(fa.ERRORS["config_not_found"], show_alert=True)
        return

    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.BACK, callback_data="my_services:list")
    await callback.message.answer(
        fa.SUB_LINK_MSG.format(url=config.subscription_url),
        reply_markup=builder.as_markup(),
    )
