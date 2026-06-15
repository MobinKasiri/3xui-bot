from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import fa
from app.bot.utils.jalali import to_jalali_full
from app.bot.utils.keyboards import back_to_menu_keyboard
from app.bot.utils.persian import format_toman
from app.db.models import User
from app.db.models.transaction import Transaction, TX_BULK, TX_PENDING

logger = logging.getLogger(__name__)
router = Router(name="bulk")

DURATION_OPTIONS = [("30", "۱ ماهه"), ("60", "۲ ماهه"), ("90", "۳ ماهه"), ("180", "۶ ماهه")]


class BulkStates(StatesGroup):
    waiting_receipt = State()


def _bulk_plans_keyboard(bulk_plans: dict) -> object:
    builder = InlineKeyboardBuilder()
    popular_key = "bulk_50g"
    for key, plan in bulk_plans.items():
        star = fa.BULK_POPULAR if key == popular_key else ""
        label = f"{plan['name']}{star} — {format_toman(plan['price'])} تومان"
        builder.button(text=label, callback_data=f"bulk:plan:{key}")
    builder.button(text=fa.BACK_TO_MENU, callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "bulk:start")
async def cb_bulk_start(callback: CallbackQuery, **kwargs) -> None:
    config_obj = kwargs.get("config")
    bulk_plans = config_obj.pricing.BULK_PLANS if config_obj else {}
    lines = [fa.BULK_HEADER]
    for key, plan in bulk_plans.items():
        per_gb = plan["price"] // plan["traffic_gb"]
        lines.append(fa.BULK_PLAN_ROW.format(
            name=plan["name"],
            star=fa.BULK_POPULAR if key == "bulk_50g" else "",
            price=format_toman(plan["price"]),
            per_gb=format_toman(per_gb),
        ))
    await callback.message.edit_text("\n".join(lines), reply_markup=_bulk_plans_keyboard(bulk_plans))
    await callback.answer()


@router.callback_query(F.data.startswith("bulk:plan:"))
async def cb_bulk_plan(callback: CallbackQuery, **kwargs) -> None:
    plan_key = callback.data.split(":", 2)[2]
    builder = InlineKeyboardBuilder()
    for days, label in DURATION_OPTIONS:
        builder.button(text=label, callback_data=f"bulk:duration:{plan_key}:{days}")
    builder.button(text=fa.BACK, callback_data="bulk:start")
    builder.adjust(2, 2, 1)
    await callback.message.edit_text(fa.BULK_SELECT_DURATION, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("bulk:duration:"))
async def cb_bulk_duration(callback: CallbackQuery, **kwargs) -> None:
    parts = callback.data.split(":")
    plan_key, days_str = parts[2], parts[3]
    config_obj = kwargs.get("config")
    bulk_plans = config_obj.pricing.BULK_PLANS if config_obj else {}
    plan = bulk_plans.get(plan_key)
    if not plan:
        await callback.answer(fa.ERRORS["not_found"], show_alert=True)
        return

    days = int(days_str)
    months = max(1, days // 30)
    total_price = plan["price"] * months

    text = fa.BULK_SUMMARY.format(
        plan_name=plan["name"],
        traffic_gb=plan["traffic_gb"],
        duration_days=days,
        total_price=format_toman(total_price),
    )
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.PAY_CARD_BTN, callback_data=f"bulk:pay:{plan_key}:{days}:{total_price}")
    builder.button(text=fa.BACK, callback_data=f"bulk:plan:{plan_key}")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("bulk:pay:"))
async def cb_bulk_pay(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    parts = callback.data.split(":")
    plan_key, days_str, total_price_str = parts[2], parts[3], parts[4]
    config_obj = kwargs.get("config")
    bulk_plans = config_obj.pricing.BULK_PLANS if config_obj else {}
    plan = bulk_plans.get(plan_key)
    if not plan:
        await callback.answer(fa.ERRORS["not_found"], show_alert=True)
        return

    total_price = int(total_price_str)
    days = int(days_str)
    card_num = config_obj.payment.CARD_NUMBER if config_obj else "XXXX"
    card_owner = config_obj.payment.CARD_OWNER if config_obj else "—"

    await state.set_state(BulkStates.waiting_receipt)
    await state.update_data(plan_key=plan_key, days=days, total_price=total_price)

    from app.bot.i18n.fa import PAYMENT_CARD_DETAIL
    await callback.message.edit_text(
        PAYMENT_CARD_DETAIL.format(
            amount=format_toman(total_price),
            card_number=card_num,
            card_owner=card_owner,
        ),
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.message(BulkStates.waiting_receipt)
async def on_bulk_receipt(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    **kwargs,
) -> None:
    config_obj = kwargs.get("config")
    data = await state.get_data()
    plan_key = data.get("plan_key")
    days = data.get("days", 30)
    total_price = data.get("total_price", 0)

    bulk_plans = config_obj.pricing.BULK_PLANS if config_obj else {}
    plan = bulk_plans.get(plan_key)
    if not plan:
        await state.clear()
        await message.answer(fa.ERRORS["general"])
        return

    receipt_photo: str | None = None
    receipt_text: str | None = None
    if message.photo:
        receipt_photo = message.photo[-1].file_id
    elif message.text:
        receipt_text = message.text
    else:
        await message.answer("لطفاً عکس رسید یا متن رسید را ارسال کنید.")
        return

    tx = await Transaction.create(
        session,
        user_id=user.tg_id,
        amount=total_price,
        type=TX_BULK,
        description=f"خرید عمده {plan['name']} — {days} روز",
        plan_key=plan_key,
        status=TX_PENDING,
        payment_receipt=receipt_photo or receipt_text,
    )
    await state.clear()
    await message.answer(fa.BULK_REQUEST_SENT, reply_markup=back_to_menu_keyboard())

    admin_chat_id = config_obj.payment.ADMIN_CHAT_ID if config_obj else 0
    if admin_chat_id:
        dt_jalali = to_jalali_full(datetime.now(tz=timezone.utc))
        from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
        b = IKB()
        b.button(text="✅ انجام شد", callback_data=f"admin:bulk_done:{tx.id}")
        b.button(text="❌ رد کردن", callback_data=f"admin:bulk_reject:{tx.id}")
        b.adjust(2)
        text = fa.ADMIN_BULK_FWD.format(
            name=user.full_name,
            username=user.username or "—",
            tg_id=user.tg_id,
            plan_name=plan["name"],
            traffic_gb=plan["traffic_gb"],
            duration_days=days,
            total_price=format_toman(total_price),
            datetime_jalali=dt_jalali,
            tx_id=tx.id,
        )
        try:
            if receipt_photo:
                await message.bot.send_photo(admin_chat_id, photo=receipt_photo, caption=text, parse_mode="HTML", reply_markup=b.as_markup())
            else:
                await message.bot.send_message(admin_chat_id, text + (f"\n\n📝 رسید:\n<code>{receipt_text}</code>" if receipt_text else ""), parse_mode="HTML", reply_markup=b.as_markup())
        except Exception as e:
            logger.error(f"Failed to forward bulk order to admin: {e}")
