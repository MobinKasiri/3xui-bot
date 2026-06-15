from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message


class IsAdmin(BaseFilter):
    _admin_ids: list[int] = []

    @classmethod
    def set_admins(cls, admin_ids: list[int]) -> None:
        cls._admin_ids = admin_ids

    async def __call__(self, message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in self._admin_ids
