"""Shared inline-keyboard builders."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.i18n.fa import BACK, BACK_TO_MENU, CANCEL


def back_keyboard(callback: str = "main_menu") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=BACK, callback_data=callback)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=BACK_TO_MENU, callback_data="main_menu")
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=CANCEL, callback_data="main_menu")
    return builder.as_markup()


def confirm_cancel_keyboard(confirm_cb: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ تایید", callback_data=confirm_cb)
    builder.button(text=CANCEL, callback_data="main_menu")
    builder.adjust(2)
    return builder.as_markup()
