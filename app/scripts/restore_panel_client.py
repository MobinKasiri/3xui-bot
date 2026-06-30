#!/usr/bin/env python3
"""Recreate 3X-UI panel clients from bot vpn_configs (no user message, no bot DB writes).

Run inside the bot container:

  ./scripts/restore-panel-client.sh --list-missing
  ./scripts/restore-panel-client.sh --config-id 42 --dry-run
  ./scripts/restore-panel-client.sh --config-id 42 --config-id 43

See docs/MANUAL_PANEL_CLIENT.md
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.services.bootstrap import bootstrap_with_retries, close_xui, ensure_vpn_service
from app.bot.services.restore_panel_client import (
    RestorePanelClientResult,
    list_missing_panel_clients,
    restore_panel_client_from_config,
)
from app.bot.services.xui_api import XUIError
from app.config import load_config


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Restore deleted 3X-UI clients from bot vpn_configs",
    )
    p.add_argument(
        "--config-id",
        type=int,
        action="append",
        dest="config_ids",
        help="vpn_configs.id from manage panel (repeatable)",
    )
    p.add_argument(
        "--email",
        action="append",
        dest="emails",
        help="panel_email (repeatable)",
    )
    p.add_argument(
        "--list-missing",
        action="store_true",
        help="List bot configs missing on the panel (newest first)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only — do not create panel clients",
    )
    p.add_argument(
        "--no-node-sync",
        action="store_true",
        help="Skip UK/US/SG node pull-sync after restore",
    )
    return p.parse_args()


def _print_result(result: RestorePanelClientResult) -> None:
    prefix = "Would restore" if result.dry_run else "Restored"
    print(f"{prefix}:")
    print(f"  config id:      {result.config_id}")
    print(f"  service name:   {result.service_name}")
    print(f"  panel email:    {result.panel_email}")
    print(f"  subscription:   {result.sub_url}")
    print(f"  uuid:           {result.panel_uuid}")
    print(f"  inbounds:       {result.inbound_ids}")


def _print_missing_table(configs) -> None:
    if not configs:
        print("No missing panel clients — every bot config exists on 3X-UI.")
        return
    print(f"Missing on panel ({len(configs)}):")
    for cfg in configs:
        print(
            f"  id={cfg.id}  user={cfg.user_id}  name={cfg.service_name!r}  "
            f"email={cfg.panel_email!r}  sub={cfg.subscription_id}"
        )


async def main() -> int:
    args = _parse_args()
    config_ids = args.config_ids or []
    emails = [e.strip() for e in (args.emails or []) if e.strip()]

    if not args.list_missing and not config_ids and not emails:
        print(
            "Provide --list-missing and/or --config-id / --email",
            file=sys.stderr,
        )
        return 1

    app_config = load_config()
    if not await bootstrap_with_retries(app_config):
        print("Panel bootstrap failed — check XUI_* in .env", file=sys.stderr)
        return 1

    vpn = await ensure_vpn_service(app_config)
    if vpn is None:
        print("VPN service unavailable", file=sys.stderr)
        await close_xui()
        return 1

    engine = create_async_engine(app_config.database.URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    exit_code = 0

    try:
        async with session_factory() as session:
            if args.list_missing:
                missing = await list_missing_panel_clients(session, vpn=vpn)
                _print_missing_table(missing)

            targets: list[tuple[int | None, str | None]] = []
            for cid in config_ids:
                targets.append((cid, None))
            for email in emails:
                targets.append((None, email))

            for config_id, email in targets:
                try:
                    result = await restore_panel_client_from_config(
                        session,
                        vpn=vpn,
                        config_id=config_id,
                        panel_email=email,
                        dry_run=args.dry_run,
                        sync_nodes=not args.no_node_sync,
                    )
                    _print_result(result)
                    print()
                except (ValueError, XUIError) as exc:
                    label = config_id if config_id is not None else email
                    print(f"Error ({label}): {exc}", file=sys.stderr)
                    exit_code = 1
    finally:
        await close_xui()
        await engine.dispose()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
