"""
VPN Config service — creates, renews, and deletes configs using the XUI API.
All 3X-UI calls go through xui_api.XUIApiService; no raw aiohttp here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.services.xui_api import XUIApiService, ClientAddPayload, XUIError
from app.bot.utils.ids import make_panel_email, make_uuid
from app.bot.utils.jalali import add_days_ms, ms_to_datetime, now_ms
from app.db.models import VPNConfig

logger = logging.getLogger(__name__)

GB = 1024 ** 3
MB = 1024 ** 2


@dataclass
class VPNConfigResult:
    config: VPNConfig
    subscription_url: str


class VPNService:
    def __init__(
        self,
        xui: XUIApiService,
        ws_inbound_id: int,
        reality_inbound_id: int,
        sub_base_url: str,
    ) -> None:
        self.xui = xui
        self.ws_id = ws_inbound_id
        self.reality_id = reality_inbound_id
        self.sub_base_url = sub_base_url.rstrip("/") + "/"

    async def create_config(
        self,
        session: AsyncSession,
        user_id: int,
        plan_key: str,
        traffic_mb: int,
        duration_days: int,
        tg_id: int,
        is_trial: bool = False,
        bonus_mb: int = 0,
    ) -> VPNConfigResult:
        """
        Create a VPN config on both WS + Reality inbounds with the same UUID/sub_id.
        Rolls back WS client if Reality fails.
        Returns VPNConfigResult with the persisted DB row.
        """
        email = make_panel_email(user_id)
        panel_uuid = make_uuid()
        sub_id = make_uuid().replace("-", "")[:20]

        total_mb = traffic_mb + bonus_mb
        total_bytes = total_mb * MB
        expiry_ms = add_days_ms(0, duration_days)
        expiry_dt = ms_to_datetime(expiry_ms)

        # ── 1. Add WS client ─────────────────────────────────────────────────
        ws_payload = ClientAddPayload(
            email=email,
            uuid=panel_uuid,
            sub_id=sub_id,
            total_bytes=total_bytes,
            expiry_ms=expiry_ms,
            flow="",
            inbound_ids=[self.ws_id],
            tg_id=tg_id,
        )
        await self.xui.add_client(ws_payload)
        logger.info(f"WS client created for user {user_id}: {email}")

        # ── 2. Add Reality client (same UUID; rollback WS if it fails) ────────
        try:
            reality_payload = ClientAddPayload(
                email=email,
                uuid=panel_uuid,
                sub_id=sub_id,
                total_bytes=total_bytes,
                expiry_ms=expiry_ms,
                flow="xtls-rprx-vision",
                inbound_ids=[self.reality_id],
                tg_id=tg_id,
            )
            await self.xui.add_client(reality_payload)
            logger.info(f"Reality client created for user {user_id}: {email}")
        except XUIError as e:
            logger.error(f"Reality create failed for {email}, rolling back WS client. Error: {e}")
            try:
                await self.xui.delete_client(email)
            except Exception as rollback_err:
                logger.error(f"Rollback also failed: {rollback_err}")
            raise

        sub_url = self.sub_base_url + sub_id

        config = await VPNConfig.create(
            session,
            user_id=user_id,
            panel_email=email,
            panel_uuid=panel_uuid,
            subscription_id=sub_id,
            subscription_url=sub_url,
            traffic_limit_bytes=total_bytes,
            traffic_used_bytes=0,
            expiry_date=expiry_dt,
            is_trial=is_trial,
            is_active=True,
            plan_key=plan_key,
        )
        return VPNConfigResult(config=config, subscription_url=sub_url)

    async def renew_config(
        self,
        session: AsyncSession,
        config: VPNConfig,
        plan_traffic_mb: int,
        plan_days: int,
    ) -> VPNConfig:
        """
        Renew an existing config:
        - Fetch live traffic from panel to get actual used bytes
        - New traffic = remaining + new plan (carry-over)
        - New expiry = max(now, current_expiry) + plan_days
        - Update on panel (same email/UUID/sub_id → subscription URL unchanged)
        - Update DB row
        """
        try:
            live = await self.xui.get_client_traffic(config.panel_email)
            used_bytes = live.used_bytes
        except XUIError:
            used_bytes = config.traffic_used_bytes

        remaining = max(0, config.traffic_limit_bytes - used_bytes)
        new_total_bytes = remaining + (plan_traffic_mb * MB)

        # Extend from max(now, expiry)
        current_ms = int(config.expiry_date.timestamp() * 1000) if config.expiry_date else 0
        new_expiry_ms = add_days_ms(max(current_ms, now_ms()), plan_days)
        new_expiry_dt = ms_to_datetime(new_expiry_ms)

        await self.xui.update_client(
            config.panel_email,
            total_bytes=new_total_bytes,
            expiry_ms=new_expiry_ms,
            flow="xtls-rprx-vision" if "reality" in config.plan_key.lower() else "",
            tg_id=config.user_id,
        )

        from datetime import datetime
        await VPNConfig.update(
            session,
            config.id,
            traffic_limit_bytes=new_total_bytes,
            traffic_used_bytes=used_bytes,
            expiry_date=new_expiry_dt,
            is_active=True,
            renewed_at=datetime.now(tz=timezone.utc),
        )
        await session.refresh(config)
        return config

    async def delete_config(self, session: AsyncSession, config: VPNConfig) -> None:
        """Delete a config from the panel and mark it inactive in the DB."""
        try:
            await self.xui.delete_client(config.panel_email)
        except XUIError as e:
            logger.warning(f"Panel delete failed for {config.panel_email}: {e}")
        await VPNConfig.update(session, config.id, is_active=False)
