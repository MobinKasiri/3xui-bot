from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ContentType, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import fa
from app.bot.services.notifications import forward_payment_to_admin
from app.bot.utils.jalali import to_jalali
from app.bot.utils.keyboards import back_to_menu_keyboard
from app.bot.utils.persian import format_toman, to_persian_digits
from app.db.models import User
from app.db.models.transaction import (
    Transaction, TX_WALLET_TOPUP, TX_PENDING, TX_CONFIRMED
)

logger = logging.getLogger(__name__)
router = Router(name="wallet")

MIN_TOPUP = 10_000

PRESET_AMOUNTS = [50_000, 100_000, 200_000, 500_000]


class WalletStates(StatesGroup):
    waiting_custom_amount = State()
    waiting_topup_receipt = State()


def _wallet_home_keyboard() -> object:
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.WALLET_TOPUP_BTN, callback_data="wallet:topup")
    builder.button(text=fa.WALLET_HISTORY_BTN, callback_data="wallet:history:0")
    builder.button(text=fa.BACK_TO_MENU, callback_data="main_menu")
    builder.adjust(2, 1)
    return builder.as_markup()


@router.callback_query(F.data == "wallet:home")
async def cb_wallet_home(callback: CallbackQuery, user: User, session: AsyncSession, **kwargs) -> None:
    txs = await Transaction.get_for_user(session, user.tg_id, limit=5)
    tx_lines = []
    for tx in txs:
        date = to_jalali(tx.created_at) if tx.created_at else "—"
        if tx.amount >= 0:
            tx_lines.append(fa.WALLET_TX_ROW_CREDIT.format(
                desc=tx.description or tx.type,
                amount=format_toman(tx.amount),
                date=date,
            ))
        else:
            tx_lines.append(fa.WALLET_TX_ROW_DEBIT.format(
                desc=tx.description or tx.type,
                amount=format_toman(abs(tx.amount)),
                date=date,
            ))

    tx_text = "\n".join(tx_lines) if tx_lines else fa.WALLET_NO_TX
    text = fa.WALLET_HEADER.format(balance=format_toman(user.balance)) + tx_text
    await callback.message.edit_text(text, reply_markup=_wallet_home_keyboard())
    await callback.answer()


@router.callback_query(F.data == "wallet:topup")
async def cb_wallet_topup(callback: CallbackQuery, **kwargs) -> None:
    builder = InlineKeyboardBuilder()
    for amount in PRESET_AMOUNTS:
        builder.button(
            text=f"{format_toman(amount)} تومان",
            callback_data=f"wallet:topup_amount:{amount}",
        )
    builder.button(text=fa.WALLET_TOPUP_CUSTOM_BTN, callback_data="wallet:topup_custom")
    builder.button(text=fa.BACK, callback_data="wallet:home")
    builder.adjust(2, 2, 1, 1)
    await callback.message.edit_text(fa.WALLET_TOPUP_AMOUNTS, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "wallet:topup_custom")
async def cb_topup_custom(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    await state.set_state(WalletStates.waiting_custom_amount)
    await callback.message.edit_text(fa.WALLET_TOPUP_CUSTOM_PROMPT, reply_markup=back_to_menu_keyboard())
    await callback.answer()


@router.message(WalletStates.waiting_custom_amount)
async def on_custom_amount(message: Message, state: FSMContext, **kwargs) -> None:
    config = kwargs.get("config")
    try:
        amount = int(message.text.strip().replace(",", "").replace("٬", ""))
    except (ValueError, AttributeError):
        await message.answer(fa.WALLET_TOPUP_INVALID)
        return

    if amount <= 0:
        await message.answer(fa.WALLET_TOPUP_INVALID)
        return
    if amount < MIN_TOPUP:
        await message.answer(fa.WALLET_TOPUP_MIN.format(min_amount=format_toman(MIN_TOPUP)))
        return

    await state.update_data(topup_amount=amount)
    await state.set_state(WalletStates.waiting_topup_receipt)

    card_num = config.payment.CARD_NUMBER if config else "XXXX"
    card_owner = config.payment.CARD_OWNER if config else "—"

    from app.bot.i18n.fa import PAYMENT_CARD_DETAIL
    await message.answer(
        PAYMENT_CARD_DETAIL.format(
            amount=format_toman(amount),
            card_number=card_num,
            card_owner=card_owner,
        ),
        reply_markup=back_to_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("wallet:topup_amount:"))
async def cb_topup_amount(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    config = kwargs.get("config")
    amount = int(callback.data.split(":")[-1])
    await state.update_data(topup_amount=amount)
    await state.set_state(WalletStates.waiting_topup_receipt)

    card_num = config.payment.CARD_NUMBER if config else "XXXX"
    card_owner = config.payment.CARD_OWNER if config else "—"

    from app.bot.i18n.fa import PAYMENT_CARD_DETAIL
    await callback.message.edit_text(
        PAYMENT_CARD_DETAIL.format(
            amount=format_toman(amount),
            card_number=card_num,
            card_owner=card_owner,
        ),
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.message(WalletStates.waiting_topup_receipt)
async def on_topup_receipt(message: Message, user: User, session: AsyncSession, state: FSMContext, **kwargs) -> None:
    config = kwargs.get("config")
    data = await state.get_data()
    amount = data.get("topup_amount", 0)

    receipt_photo: str | None = None
    receipt_text: str | None = None

    if message.photo:
        receipt_photo = message.photo[-1].file_id
    elif message.text:
        receipt_text = message.text
    else:
        await message.answer("لطفاً عکس رسید یا متن را ارسال کنید.")
        return

    tx = await Transaction.create(
        session,
        user_id=user.tg_id,
        amount=amount,
        type=TX_WALLET_TOPUP,
        description=f"شارژ کیف پول {format_toman(amount)} تومان",
        status=TX_PENDING,
        payment_receipt=receipt_photo or receipt_text,
    )
    await state.clear()
    await message.answer(fa.RECEIPT_RECEIVED, reply_markup=back_to_menu_keyboard())

    admin_chat_id = config.payment.ADMIN_CHAT_ID if config else 0
    if admin_chat_id:
        from datetime import datetime, timezone
        from app.bot.utils.jalali import to_jalali_full
        dt_jalali = to_jalali_full(datetime.now(tz=timezone.utc))
        from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
        builder = IKB()
        builder.button(text=fa.ADMIN_APPROVE_BTN, callback_data=f"admin:approve_topup:{tx.id}")
        builder.button(text=fa.ADMIN_REJECT_BTN, callback_data=f"admin:reject_topup:{tx.id}")
        builder.adjust(2)
        markup = builder.as_markup()
        text = fa.ADMIN_WALLET_FWD.format(
            name=user.full_name,
            username=user.username or "—",
            tg_id=user.tg_id,
            amount=format_toman(amount),
            datetime_jalali=dt_jalali,
            tx_id=tx.id,
        )
        try:
            if receipt_photo:
                await message.bot.send_photo(admin_chat_id, photo=receipt_photo, caption=text, parse_mode="HTML", reply_markup=markup)
            else:
                await message.bot.send_message(admin_chat_id, text + (f"\n\n📝 رسید:\n<code>{receipt_text}</code>" if receipt_text else ""), parse_mode="HTML", reply_markup=markup)
        except Exception as e:
            logger.error(f"Failed to forward topup to admin: {e}")


@router.callback_query(F.data.startswith("admin:approve_topup:"))
async def cb_admin_approve_topup(callback: CallbackQuery, user: User, session: AsyncSession, **kwargs) -> None:
    config = kwargs.get("config")
    admin_ids = config.bot.ADMINS if config else []
    if user.tg_id not in admin_ids:
        await callback.answer(fa.ERRORS["admin_only"], show_alert=True)
        return

    tx_id = int(callback.data.split(":")[-1])
    tx = await Transaction.get(session, tx_id)
    if not tx or tx.status != TX_PENDING:
        await callback.answer("تراکنش قبلاً پردازش شده است.", show_alert=True)
        return

    from app.bot.services.wallet import credit
    await credit(session, tx.user_id, tx.amount, f"شارژ کیف پول #{tx.id}", tx_type=TX_WALLET_TOPUP)
    # Update original tx
    from datetime import datetime
    await Transaction.update(session, tx_id, status=TX_CONFIRMED, confirmed_at=datetime.utcnow())

    buyer = await User.get(session, tx.user_id)
    if buyer:
        await callback.bot.send_message(
            buyer.tg_id,
            fa.WALLET_CHARGED.format(balance=format_toman(buyer.balance + tx.amount)),
            parse_mode="HTML",
        )

    try:
        await callback.message.edit_caption((callback.message.caption or "") + "\n\n✅ شارژ تایید شد.")
    except Exception:
        await callback.message.edit_text((callback.message.text or "") + "\n\n✅ شارژ تایید شد.")
    await callback.answer("✅ کیف پول شارژ شد.")


@router.callback_query(F.data.startswith("admin:reject_topup:"))
async def cb_admin_reject_topup(callback: CallbackQuery, user: User, session: AsyncSession, **kwargs) -> None:
    config = kwargs.get("config")
    admin_ids = config.bot.ADMINS if config else []
    if user.tg_id not in admin_ids:
        await callback.answer(fa.ERRORS["admin_only"], show_alert=True)
        return

    tx_id = int(callback.data.split(":")[-1])
    tx = await Transaction.get(session, tx_id)
    if not tx or tx.status != TX_PENDING:
        await callback.answer("تراکنش قبلاً پردازش شده است.", show_alert=True)
        return

    from app.db.models.transaction import TX_REJECTED
    await Transaction.update(session, tx_id, status=TX_REJECTED)

    buyer = await User.get(session, tx.user_id)
    if buyer:
        await callback.bot.send_message(
            buyer.tg_id,
            fa.PURCHASE_REJECTED.format(reason="شارژ کیف پول تایید نشد."),
            parse_mode="HTML",
        )

    try:
        await callback.message.edit_caption((callback.message.caption or "") + "\n\n❌ رد شد.")
    except Exception:
        await callback.message.edit_text((callback.message.text or "") + "\n\n❌ رد شد.")
    await callback.answer("❌ رد شد.")


@router.callback_query(F.data.startswith("wallet:history:"))
async def cb_wallet_history(callback: CallbackQuery, user: User, session: AsyncSession, **kwargs) -> None:
    page = int(callback.data.split(":")[-1])
    limit = 10
    offset = page * limit
    txs = await Transaction.get_for_user(session, user.tg_id, limit=limit + 1)
    txs = txs[offset:offset + limit]
    has_more = len(txs) > limit

    if not txs:
        await callback.answer("تراکنش بیشتری وجود ندارد.", show_alert=True)
        return

    lines = []
    for tx in txs[:limit]:
        date = to_jalali(tx.created_at) if tx.created_at else "—"
        if tx.amount >= 0:
            lines.append(fa.WALLET_TX_ROW_CREDIT.format(desc=tx.description or tx.type, amount=format_toman(tx.amount), date=date))
        else:
            lines.append(fa.WALLET_TX_ROW_DEBIT.format(desc=tx.description or tx.type, amount=format_toman(abs(tx.amount)), date=date))

    builder = InlineKeyboardBuilder()
    if has_more:
        builder.button(text="صفحه بعد ▶️", callback_data=f"wallet:history:{page+1}")
    if page > 0:
        builder.button(text="◀️ صفحه قبل", callback_data=f"wallet:history:{page-1}")
    builder.button(text=fa.BACK, callback_data="wallet:home")
    builder.adjust(2, 1)

    await callback.message.edit_text(
        f"📋 <b>تاریخچه تراکنش‌ها (صفحه {to_persian_digits(page+1)})</b>\n\n" + "\n".join(lines),
        reply_markup=builder.as_markup(),
    )
    await callback.answer()
