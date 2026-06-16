"""Shared inline-keyboard builders."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.i18n import fa


def back_keyboard(callback: str = "main_menu") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.BACK, callback_data=callback)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.BACK_TO_MENU, callback_data="main_menu")
    return builder.as_markup()


def home_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.HOME, callback_data="main_menu")
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.CANCEL, callback_data="cancel_fsm")
    return builder.as_markup()


def confirm_cancel_keyboard(confirm_cb: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.CONFIRM, callback_data=confirm_cb)
    builder.button(text=fa.CANCEL, callback_data="cancel_fsm")
    builder.adjust(2)
    return builder.as_markup()
