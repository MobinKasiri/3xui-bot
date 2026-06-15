"""Send Persian notifications to users and forward events to admin chats."""
from __future__ import annotations

import logging

from aiogram import Bot

from app.bot.i18n import fa
from app.bot.utils.jalali import to_jalali, now_ms
from app.bot.utils.persian import format_toman

logger = logging.getLogger(__name__)


async def notify_user(bot: Bot, user_id: int, text: str, reply_markup=None) -> bool:
    """Send a message to a user. Returns True on success."""
    try:
        await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.warning(f"Failed to notify user {user_id}: {e}")
        return False


async def forward_payment_to_admin(
    bot: Bot,
    admin_chat_id: int,
    tx_id: int,
    user_name: str,
    username: str | None,
    tg_id: int,
    plan_name: str,
    amount: int,
    receipt_photo: str | None,
    receipt_text: str | None,
    approve_cb: str,
    reject_cb: str,
) -> None:
    from datetime import datetime, timezone
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    dt = datetime.now(tz=timezone.utc)
    dt_jalali = to_jalali(dt)

    text = fa.ADMIN_PAYMENT_FWD.format(
        name=user_name,
        username=username or "—",
        tg_id=tg_id,
        plan_name=plan_name,
        amount=format_toman(amount),
        datetime_jalali=dt_jalali,
        tx_id=tx_id,
    )

    builder = InlineKeyboardBuilder()
    builder.button(text=fa.ADMIN_APPROVE_BTN, callback_data=approve_cb)
    builder.button(text=fa.ADMIN_REJECT_BTN, callback_data=reject_cb)
    builder.adjust(2)
    markup = builder.as_markup()

    try:
        if receipt_photo:
            await bot.send_photo(
                admin_chat_id,
                photo=receipt_photo,
                caption=text,
                parse_mode="HTML",
                reply_markup=markup,
            )
        else:
            await bot.send_message(
                admin_chat_id,
                text + (f"\n\n📝 متن رسید:\n<code>{receipt_text}</code>" if receipt_text else ""),
                parse_mode="HTML",
                reply_markup=markup,
            )
    except Exception as e:
        logger.error(f"Failed to forward payment to admin {admin_chat_id}: {e}")
