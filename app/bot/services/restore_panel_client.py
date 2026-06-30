"""Recreate 3X-UI panel clients from existing bot VPNConfig rows.

Read-only on the bot database — no Telegram messages.
Preserves panel_email, panel_uuid, and subscription_id so existing sub URLs keep working.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.services.node_sync import schedule_node_sync
from app.bot.services.vpn import VPNService
from app.bot.services.xui_api import ClientAddPayload, XUIError, XUINotFound
from app.bot.utils.jalali import datetime_to_ms, start_after_first_use_ms
from app.db.models import VPNConfig

logger = logging.getLogger(__name__)


@dataclass
class RestorePanelClientResult:
    config_id: int
    panel_email: str
    service_name: str
    subscription_id: str
    panel_uuid: str
    sub_url: str
    restored: bool
    dry_run: bool
    inbound_ids: list[int]


def expiry_ms_for_config(cfg: VPNConfig, *, start_after_first_use: bool) -> int:
    if cfg.expiry_date is not None:
        return datetime_to_ms(cfg.expiry_date)
    if start_after_first_use:
        days = cfg.plan_days or 30
        return start_after_first_use_ms(days)
    return 0


async def load_config(
    session: AsyncSession,
    *,
    config_id: int | None = None,
    panel_email: str | None = None,
) -> VPNConfig:
    if config_id is not None:
        cfg = await VPNConfig.get(session, config_id)
        if cfg is None:
            raise ValueError(f"vpn_configs id={config_id} not found in bot database")
        return cfg
    email = (panel_email or "").strip()
    if not email:
        raise ValueError("config_id or panel_email is required")
    cfg = await VPNConfig.get_by_email(session, email)
    if cfg is None:
        raise ValueError(f"vpn_configs panel_email={email!r} not found in bot database")
    return cfg


async def restore_panel_client_from_config(
    session: AsyncSession,
    *,
    vpn: VPNService,
    config_id: int | None = None,
    panel_email: str | None = None,
    dry_run: bool = False,
    sync_nodes: bool = True,
) -> RestorePanelClientResult:
    """
    Create the panel client row that matches an existing bot VPNConfig.

    Raises ValueError for validation errors; XUIError on panel API failure.
    """
    cfg = await load_config(session, config_id=config_id, panel_email=panel_email)
    email = cfg.panel_email.strip()
    sub_id = cfg.subscription_id.strip()
    vless_uuid = cfg.panel_uuid.strip()

    if not email or not sub_id or not vless_uuid:
        raise ValueError(
            f"Config id={cfg.id} is missing panel_email, subscription_id, or panel_uuid"
        )

    if await vpn.xui.client_exists(email):
        raise ValueError(
            f"Panel client {email!r} already exists — nothing to restore "
            f"(bot config id={cfg.id})"
        )

    inbound_ids = await vpn._active_inbound_ids()
    if not inbound_ids:
        raise ValueError("No active panel inbounds — check XUI bootstrap")

    expiry_ms = expiry_ms_for_config(cfg, start_after_first_use=vpn.start_after_first_use)
    sub_url = vpn.sub_url(sub_id)

    result = RestorePanelClientResult(
        config_id=cfg.id,
        panel_email=email,
        service_name=cfg.service_name,
        subscription_id=sub_id,
        panel_uuid=vless_uuid,
        sub_url=sub_url,
        restored=False,
        dry_run=dry_run,
        inbound_ids=inbound_ids,
    )

    logger.info(
        "Restore panel client: config_id=%s email=%s sub=%s uuid=%s dry_run=%s",
        cfg.id,
        email,
        sub_id,
        vless_uuid,
        dry_run,
    )

    if dry_run:
        return result

    payload = ClientAddPayload(
        email=email,
        uuid=vless_uuid,
        sub_id=sub_id,
        total_bytes=cfg.traffic_limit_bytes,
        expiry_ms=expiry_ms,
        flow="",
        inbound_ids=inbound_ids,
        enable=bool(cfg.is_active),
        tg_id=int(cfg.user_id),
        comment=cfg.service_name,
    )

    try:
        await vpn.xui.add_client(payload)
        resolved_uuid = await vpn.xui.resolve_client_uuid(email, hint=vless_uuid)
        if resolved_uuid and resolved_uuid != vless_uuid:
            raise XUIError(
                f"Panel returned different uuid for {email}: "
                f"expected {vless_uuid}, got {resolved_uuid}"
            )
        await vpn.xui.ensure_client_on_inbounds(email, vless_uuid, inbound_ids)
    except XUIError:
        try:
            if await vpn.xui.client_exists(email):
                await vpn.xui.delete_client(email)
        except Exception as cleanup_err:
            logger.warning("Rollback delete failed for %s: %s", email, cleanup_err)
        raise

    if not await vpn.xui.client_exists(email):
        raise XUIError(f"Panel client {email!r} not visible after restore")

    try:
        links = await vpn.xui.get_sub_links(sub_id)
        if not links:
            logger.warning("Sub id %s restored but get_sub_links returned empty", sub_id)
    except XUINotFound:
        logger.warning("Sub id %s not found immediately after restore", sub_id)
    except XUIError as exc:
        logger.warning("Could not verify sub links for %s: %s", sub_id, exc)

    if sync_nodes and vpn._node_sync_enabled:
        schedule_node_sync(
            vpn.xui,
            ssh_user=vpn._node_ssh_user,
            ssh_port=vpn._node_ssh_port,
            ssh_identity=vpn._node_ssh_identity,
        )

    await vpn._signal_direct_nodes()
    result.restored = True
    logger.info("Restored panel client %s (config id=%s)", email, cfg.id)
    return result


async def list_missing_panel_clients(session: AsyncSession, *, vpn: VPNService) -> list[VPNConfig]:
    """Bot configs whose panel_email is absent from 3X-UI."""
    missing: list[VPNConfig] = []
    for cfg in await VPNConfig.get_all(session):
        try:
            exists = await vpn.xui.client_exists(cfg.panel_email)
        except XUIError:
            exists = False
        if not exists:
            missing.append(cfg)
    missing.sort(key=lambda c: c.created_at, reverse=True)
    return missing
