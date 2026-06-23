"""3X-UI connection settings — no Telegram/aiogram imports."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class XUIConfig:
    HOST: str
    PATH: str
    USERNAME: str
    PASSWORD: str
    TOKEN: str | None
    SUB_BASE_URL: str
    INBOUND_FILTER: tuple[str, ...] = ()
    START_AFTER_FIRST_USE: bool = True
    DEFAULT_DURATION_DAYS: int = 30
    NODE_SYNC_ENABLED: bool = False
    NODE_SSH_USER: str = "root"
    NODE_SSH_PORT: int = 22
    NODE_SSH_IDENTITY: str = ""
    NODE_SYNC_TRIGGER_TOKEN: str = ""

    @property
    def base_url(self) -> str:
        return self.HOST.rstrip("/") + "/" + self.PATH.strip("/")
