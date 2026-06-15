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
from app.db.models import User, VPNConfig
from app.db.models.agency_request import AgencyRequest, STATUS_APPROVED, STATUS_REJECTED

logger = logging.getLogger(__name__)
router = Router(name="agency")


class AgencyStates(StatesGroup):
    waiting_message = State()


@router.callback_query(F.data == "agency:start")
async def cb_agency_start(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    await state.set_state(AgencyStates.waiting_message)
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.CANCEL, callback_data="main_menu")
    await callback.message.edit_text(fa.AGENCY_INFO, reply_markup=builder.as_markup())
    await callback.answer()


@router.message(AgencyStates.waiting_message)
async def on_agency_message(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    **kwargs,
) -> None:
    config_obj = kwargs.get("config")
    text = message.text
    if not text or len(text.strip()) < 10:
        await message.answer("لطفاً توضیحات بیشتری بنویسید (حداقل ۱۰ کاراکتر).")
        return

    req = await AgencyRequest.create(
        session,
        user_id=user.tg_id,
        message=text.strip(),
    )
    await state.clear()
    await message.answer(fa.AGENCY_SENT, reply_markup=back_to_menu_keyboard())

    admin_chat_id = config_obj.payment.AGENCY_ADMIN_CHAT_ID if config_obj else 0
    if admin_chat_id:
        config_count = len(await VPNConfig.get_for_user(session, user.tg_id))
        dt_jalali = to_jalali_full(datetime.now(tz=timezone.utc))

        builder = InlineKeyboardBuilder()
        builder.button(text=fa.ADMIN_AGENCY_APPROVE_BTN, callback_data=f"admin:agency_approve:{req.id}")
        builder.button(text=fa.ADMIN_AGENCY_REJECT_BTN, callback_data=f"admin:agency_reject:{req.id}")
        builder.adjust(2)

        fwd_text = fa.ADMIN_AGENCY_FWD.format(
            name=user.full_name,
            username=user.username or "—",
            tg_id=user.tg_id,
            datetime_jalali=dt_jalali,
            config_count=config_count,
            message=text.strip(),
            req_id=req.id,
        )
        try:
            await message.bot.send_message(
                admin_chat_id, fwd_text, parse_mode="HTML", reply_markup=builder.as_markup()
            )
        except Exception as e:
            logger.error(f"Failed to forward agency request: {e}")


@router.callback_query(F.data.startswith("admin:agency_approve:"))
async def cb_agency_approve(callback: CallbackQuery, user: User, session: AsyncSession, **kwargs) -> None:
    config_obj = kwargs.get("config")
    admin_ids = config_obj.bot.ADMINS if config_obj else []
    if user.tg_id not in admin_ids:
        await callback.answer(fa.ERRORS["admin_only"], show_alert=True)
        return

    req_id = int(callback.data.split(":")[-1])
    req = await AgencyRequest.get(session, req_id)
    if not req:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return

    await AgencyRequest.update_status(session, req_id, STATUS_APPROVED)
    await User.update(session, req.user_id, is_agent=True)

    try:
        await callback.bot.send_message(req.user_id, fa.AGENCY_APPROVED_USER, parse_mode="HTML")
    except Exception:
        pass

    await callback.message.edit_text((callback.message.text or "") + "\n\n✅ تایید شد — کاربر نماینده شد.")
    await callback.answer("✅ درخواست تایید شد.")


@router.callback_query(F.data.startswith("admin:agency_reject:"))
async def cb_agency_reject(callback: CallbackQuery, user: User, session: AsyncSession, **kwargs) -> None:
    config_obj = kwargs.get("config")
    admin_ids = config_obj.bot.ADMINS if config_obj else []
    if user.tg_id not in admin_ids:
        await callback.answer(fa.ERRORS["admin_only"], show_alert=True)
        return

    req_id = int(callback.data.split(":")[-1])
    req = await AgencyRequest.get(session, req_id)
    if not req:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return

    await AgencyRequest.update_status(session, req_id, STATUS_REJECTED)

    try:
        await callback.bot.send_message(
            req.user_id,
            fa.AGENCY_REJECTED_USER.format(reason="درخواست شما در این مرحله تایید نشد."),
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.message.edit_text((callback.message.text or "") + "\n\n❌ رد شد.")
    await callback.answer("❌ درخواست رد شد.")
