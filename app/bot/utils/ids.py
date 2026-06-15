"""Unique identifier generators for 3X-UI clients."""
import time
import uuid


def make_panel_email(tg_id: int) -> str:
    """Generate unique email for 3X-UI: u{tg_id}_{ts}@nexora.vpn"""
    ts = int(time.time())
    return f"u{tg_id}_{ts}@nexora.vpn"


def make_uuid() -> str:
    return str(uuid.uuid4())
