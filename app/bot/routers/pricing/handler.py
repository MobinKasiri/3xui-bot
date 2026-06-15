from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.i18n import fa
from app.bot.utils.persian import format_toman

router = Router(name="pricing")


@router.callback_query(F.data == "pricing:show")
async def cb_pricing(callback: CallbackQuery, **kwargs) -> None:
    config_obj = kwargs.get("config")
    plans = config_obj.pricing.PLANS if config_obj else {}

    lines = [fa.PRICING_HEADER]
    for plan in plans.values():
        per_gb = plan["price"] // plan["traffic_gb"]
        lines.append(fa.PRICING_ROW.format(
            emoji=plan["emoji"],
            name=plan["name"],
            traffic_gb=plan["traffic_gb"],
            duration_days=plan["duration_days"],
            price=format_toman(plan["price"]),
            per_gb=format_toman(per_gb),
        ))
    lines.append(fa.PRICING_FOOTER)

    builder = InlineKeyboardBuilder()
    builder.button(text=fa.MAIN_MENU_BUTTONS["purchase"], callback_data="purchase:start")
    builder.button(text=fa.BACK_TO_MENU, callback_data="main_menu")
    builder.adjust(1)

    await callback.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
    await callback.answer()
