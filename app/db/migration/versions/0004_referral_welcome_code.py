"""Add friend_welcome_code to referrals

Revision ID: 0004_referral_welcome_code
Revises: 0003_channel_gate_passed
Create Date: 2026-06-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_referral_welcome_code"
down_revision = "0003_channel_gate_passed"
branch_labels = None
depends_on = None


def _dialect() -> str:
    return op.get_bind().dialect.name


def _col_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    if _dialect() == "sqlite":
        rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
        return any(row[1] == column for row in rows)
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    )
    return result.scalar() is not None


def upgrade() -> None:
    if not _col_exists("referrals", "friend_welcome_code"):
        op.add_column(
            "referrals",
            sa.Column("friend_welcome_code", sa.String(50), nullable=True),
        )


def downgrade() -> None:
    if _col_exists("referrals", "friend_welcome_code"):
        op.drop_column("referrals", "friend_welcome_code")
