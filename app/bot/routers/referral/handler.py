from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import fa
from app.bot.utils.keyboards import back_to_menu_keyboard
from app.bot.utils.persian import to_persian_digits
from app.db.models import User
from app.db.models.referral import Referral

logger = logging.getLogger(__name__)
router = Router(name="referral")


@router.callback_query(F.data == "referral:page")
async def cb_referral_page(callback: CallbackQuery, user: User, session: AsyncSession, **kwargs) -> None:
    count = await Referral.count_for_referrer(session, user.tg_id)
    # Total bonus MB given
    from sqlalchemy import select, func
    from app.db.models.referral import Referral as R
    result = await session.execute(
        select(func.coalesce(func.sum(R.bonus_mb), 0)).where(R.referrer_id == user.tg_id, R.bonus_given == True)
    )
    total_mb = result.scalar_one() or 0

    bot_username = (await callback.bot.get_me()).username
    text = fa.REFERRAL_PAGE.format(
        bot_username=bot_username,
        referral_code=user.referral_code,
        count=to_persian_digits(count),
        total_mb=to_persian_digits(total_mb),
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text=fa.REFERRAL_SHARE_BTN,
        url=f"https://t.me/share/url?url=https://t.me/{bot_username}?start=ref_{user.referral_code}&text=با+نکسورانود+VPN+رایگان+دریافت+کن!",
    )
    builder.button(text=fa.BACK_TO_MENU, callback_data="main_menu")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), disable_web_page_preview=True)
    await callback.answer()
