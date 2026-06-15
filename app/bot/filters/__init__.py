from aiogram import Dispatcher

from .is_admin import IsAdmin
from .is_private import IsPrivate as IsPrivateChat


def register(dispatcher: Dispatcher, admin_ids: list[int]) -> None:
    IsAdmin.set_admins(admin_ids)
