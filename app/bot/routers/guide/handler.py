from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.i18n import fa

router = Router(name="guide")

_GUIDE_PAGES = {
    "guide:install":     fa.GUIDE_INSTALL,
    "guide:connect":     fa.GUIDE_CONNECT,
    "guide:bot_help":    fa.GUIDE_BOT_HELP,
    "guide:faq":         fa.GUIDE_FAQ,
    "guide:troubleshoot": fa.GUIDE_TROUBLESHOOT,
}


def _guide_main_keyboard() -> object:
    builder = InlineKeyboardBuilder()
    for key, label in fa.GUIDE_BTNS.items():
        builder.button(text=label, callback_data=f"guide:{key}")
    builder.button(text=fa.BACK_TO_MENU, callback_data="main_menu")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def _guide_back_keyboard() -> object:
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.BACK, callback_data="guide:main")
    builder.button(text=fa.BACK_TO_MENU, callback_data="main_menu")
    builder.adjust(2)
    return builder.as_markup()


@router.callback_query(F.data == "guide:main")
async def cb_guide_main(callback: CallbackQuery) -> None:
    await callback.message.edit_text(fa.GUIDE_MAIN, reply_markup=_guide_main_keyboard())
    await callback.answer()


@router.callback_query(F.data.in_(list(_GUIDE_PAGES.keys())))
async def cb_guide_page(callback: CallbackQuery) -> None:
    content = _GUIDE_PAGES.get(callback.data, "")
    await callback.message.edit_text(content, reply_markup=_guide_back_keyboard(), disable_web_page_preview=True)
    await callback.answer()
