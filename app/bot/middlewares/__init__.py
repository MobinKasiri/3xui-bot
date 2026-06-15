from aiogram import Dispatcher
from sqlalchemy.ext.asyncio import async_sessionmaker

from .database import DBSessionMiddleware
from .throttling import ThrottlingMiddleware


def register(dispatcher: Dispatcher, session: async_sessionmaker) -> None:
    for mw in [ThrottlingMiddleware(), DBSessionMiddleware(session)]:
        dispatcher.update.middleware.register(mw)
