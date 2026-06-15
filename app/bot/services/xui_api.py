"""
Raw async HTTP client for the 3X-UI v3.3.1 panel API.
All endpoints are derived from 3XUI_api.json — never guessed.

Authentication: cookie (POST /login) with auto-relogin on 401.
Optionally uses Bearer token when XUI_TOKEN is set.

All public methods return typed dataclasses or raise one of:
  XUIAuthError, XUINotFound, XUIAPIError, XUINetworkError
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiohttp

from app.config import XUIConfig

logger = logging.getLogger(__name__)


# ─── Custom exceptions ────────────────────────────────────────────────────────

class XUIError(Exception):
    """Base XUI exception."""
    persian: str = "خطایی رخ داد. لطفاً دوباره تلاش کنید."


class XUIAuthError(XUIError):
    persian = "⚠️ خطا در احراز هویت پنل. با پشتیبانی تماس بگیرید."


class XUINotFound(XUIError):
    persian = "❌ سرویس مورد نظر یافت نشد."


class XUIAPIError(XUIError):
    persian = "⚠️ خطا در ارتباط با سرور. لطفاً دقایقی دیگر تلاش کنید."


class XUINetworkError(XUIError):
    persian = "⚠️ اتصال به سرور برقرار نشد. اینترنت سرور را بررسی کنید."


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class InboundInfo:
    id: int
    remark: str
    protocol: str
    port: int
    enable: bool


@dataclass
class ClientTraffic:
    email: str
    up: int
    down: int
    total: int           # traffic limit in bytes (0 = unlimited)
    expiry_time: int     # ms timestamp (0 = never)
    enable: bool

    @property
    def used_bytes(self) -> int:
        return self.up + self.down

    @property
    def expiry_dt(self) -> datetime | None:
        if self.expiry_time == 0:
            return None
        return datetime.fromtimestamp(self.expiry_time / 1000, tz=timezone.utc)


@dataclass
class ServerStatus:
    cpu: float
    mem_current: int
    mem_total: int
    uptime: int
    xray_state: str


@dataclass
class ClientAddPayload:
    """Everything needed to create a client on the panel."""
    email: str
    uuid: str           # VLESS/VMess id
    sub_id: str         # subscription ID (same UUID)
    total_bytes: int    # 0 = unlimited
    expiry_ms: int      # ms timestamp; 0 = never
    flow: str           # "" for WS, "xtls-rprx-vision" for Reality
    inbound_ids: list[int]
    limit_ip: int = 0
    enable: bool = True
    tg_id: int = 0


# ─── XUI API Client ──────────────────────────────────────────────────────────

class XUIApiService:
    def __init__(self, config: XUIConfig) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._logged_in = False

    @property
    def _base(self) -> str:
        return self._config.base_url

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar(unsafe=True)
            headers = {}
            if self._config.TOKEN:
                headers["Authorization"] = f"Bearer {self._config.TOKEN}"
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(
                cookie_jar=jar,
                headers=headers,
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def login(self) -> None:
        """Authenticate via cookie. Raises XUIAuthError on failure."""
        session = await self._get_session()
        # Login is at {HOST}{PATH}/login  (e.g. https://host:2087/secret/login)
        url = self._base + "/login"
        payload = {
            "username": self._config.USERNAME,
            "password": self._config.PASSWORD,
            "twoFactorCode": "",
        }
        try:
            async with session.post(url, json=payload) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = None
                if not data or not data.get("success"):
                    msg = (data or {}).get("msg", f"HTTP {resp.status}")
                    raise XUIAuthError(f"Login failed: {msg}")
                self._logged_in = True
                logger.info("3X-UI panel login successful.")
        except XUIAuthError:
            raise
        except aiohttp.ClientError as e:
            raise XUINetworkError(str(e)) from e

    async def _request(
        self, method: str, path: str, *, retry: bool = True, **kwargs: Any
    ) -> dict:
        """Make an authenticated request; auto-relogin on 401."""
        if not self._logged_in and not self._config.TOKEN:
            await self.login()
        session = await self._get_session()
        url = f"{self._base}{path}"
        try:
            async with session.request(method, url, **kwargs) as resp:
                if resp.status == 401:
                    if retry:
                        self._logged_in = False
                        await self.login()
                        return await self._request(method, path, retry=False, **kwargs)
                    raise XUIAuthError("Persistent 401 after relogin.")
                if resp.status == 404:
                    raise XUINotFound(f"404 on {path}")
                data = await resp.json(content_type=None)
                if not data.get("success", True):
                    raise XUIAPIError(f"API error on {path}: {data.get('msg', '')}")
                return data
        except (XUIAuthError, XUINotFound, XUIAPIError):
            raise
        except aiohttp.ClientError as e:
            raise XUINetworkError(str(e)) from e

    # ── Inbounds ──────────────────────────────────────────────────────────────

    async def list_inbounds(self) -> list[InboundInfo]:
        """GET /panel/api/inbounds/list"""
        data = await self._request("GET", "/panel/api/inbounds/list")
        result = []
        for item in data.get("obj", []):
            result.append(InboundInfo(
                id=item["id"],
                remark=item.get("remark", ""),
                protocol=item.get("protocol", ""),
                port=item.get("port", 0),
                enable=item.get("enable", True),
            ))
        return result

    async def find_inbound_ids(
        self, ws_name: str, reality_name: str
    ) -> tuple[int, int]:
        """Return (ws_inbound_id, reality_inbound_id). Raises XUINotFound if missing."""
        inbounds = await self.list_inbounds()
        ws_id: int | None = None
        reality_id: int | None = None
        for ib in inbounds:
            if ib.remark == ws_name:
                ws_id = ib.id
            elif ib.remark == reality_name:
                reality_id = ib.id
        if ws_id is None:
            raise XUINotFound(f"Inbound '{ws_name}' not found on panel.")
        if reality_id is None:
            raise XUINotFound(f"Inbound '{reality_name}' not found on panel.")
        logger.info(f"Inbound IDs — WS: {ws_id}, Reality: {reality_id}")
        return ws_id, reality_id

    # ── Clients ───────────────────────────────────────────────────────────────

    async def add_client(self, payload: ClientAddPayload) -> None:
        """
        POST /panel/api/clients/add
        Creates the client and attaches it to all inbound_ids in one call.
        """
        body = {
            "client": {
                "email": payload.email,
                "id": payload.uuid,          # VLESS/VMess uuid field
                "subId": payload.sub_id,
                "totalGB": payload.total_bytes,
                "expiryTime": payload.expiry_ms,
                "flow": payload.flow,
                "limitIp": payload.limit_ip,
                "enable": payload.enable,
                "tgId": payload.tg_id,
            },
            "inboundIds": payload.inbound_ids,
        }
        await self._request("POST", "/panel/api/clients/add", json=body)
        logger.info(f"Client created: {payload.email} on inbounds {payload.inbound_ids}")

    async def update_client(
        self,
        email: str,
        *,
        total_bytes: int,
        expiry_ms: int,
        flow: str = "",
        limit_ip: int = 0,
        enable: bool = True,
        tg_id: int = 0,
    ) -> None:
        """
        POST /panel/api/clients/update/{email}
        Full replace — all fields required.
        """
        body = {
            "email": email,
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "flow": flow,
            "limitIp": limit_ip,
            "enable": enable,
            "tgId": tg_id,
        }
        await self._request("POST", f"/panel/api/clients/update/{email}", json=body)
        logger.info(f"Client updated: {email}")

    async def delete_client(self, email: str) -> None:
        """POST /panel/api/clients/del/{email}?keepTraffic=0"""
        await self._request("POST", f"/panel/api/clients/del/{email}", params={"keepTraffic": 0})
        logger.info(f"Client deleted: {email}")

    async def get_client_traffic(self, email: str) -> ClientTraffic:
        """GET /panel/api/clients/traffic/{email}"""
        data = await self._request("GET", f"/panel/api/clients/traffic/{email}")
        obj = data.get("obj") or {}
        if not obj:
            raise XUINotFound(f"No traffic data for {email}")
        return ClientTraffic(
            email=obj.get("email", email),
            up=obj.get("up", 0),
            down=obj.get("down", 0),
            total=obj.get("total", 0),
            expiry_time=obj.get("expiryTime", 0),
            enable=obj.get("enable", True),
        )

    async def get_client_links(self, email: str) -> list[str]:
        """GET /panel/api/clients/links/{email} — returns list of protocol URLs."""
        data = await self._request("GET", f"/panel/api/clients/links/{email}")
        obj = data.get("obj", [])
        if isinstance(obj, list):
            return obj
        return []

    async def get_sub_links(self, sub_id: str) -> list[str]:
        """GET /panel/api/clients/subLinks/{subId}"""
        data = await self._request("GET", f"/panel/api/clients/subLinks/{sub_id}")
        obj = data.get("obj", [])
        if isinstance(obj, list):
            return obj
        return []

    async def attach_client(self, email: str, inbound_ids: list[int]) -> None:
        """POST /panel/api/clients/{email}/attach"""
        await self._request(
            "POST", f"/panel/api/clients/{email}/attach",
            json={"inboundIds": inbound_ids}
        )
        logger.info(f"Client {email} attached to inbounds {inbound_ids}")

    async def detach_client(self, email: str, inbound_ids: list[int]) -> None:
        """POST /panel/api/clients/{email}/detach"""
        await self._request(
            "POST", f"/panel/api/clients/{email}/detach",
            json={"inboundIds": inbound_ids}
        )
        logger.info(f"Client {email} detached from inbounds {inbound_ids}")

    # ── Server ────────────────────────────────────────────────────────────────

    async def get_server_status(self) -> ServerStatus:
        """GET /panel/api/server/status"""
        data = await self._request("GET", "/panel/api/server/status")
        obj = data.get("obj", {})
        return ServerStatus(
            cpu=obj.get("cpu", 0.0),
            mem_current=obj.get("mem", {}).get("current", 0),
            mem_total=obj.get("mem", {}).get("total", 1),
            uptime=obj.get("uptime", 0),
            xray_state=obj.get("xray", {}).get("state", "unknown"),
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        logger.debug("XUI API session closed.")
