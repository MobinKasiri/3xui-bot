"""Discount per-user limits and allow multiple uses per user

Revision ID: 0007_discount_per_user_limits
Revises: 0006_bot_admin_notify
Create Date: 2026-06-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_discount_per_user_limits"
down_revision = "0006_bot_admin_notify"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
        return any(r[1] == column for r in rows)
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    )
    return result.scalar() is not None


def _constraint_exists(table: str, name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(sa.text(f"PRAGMA index_list({table})")).fetchall()
        return any(r[1] == name for r in rows)
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = :t AND constraint_name = :c"
        ),
        {"t": table, "c": name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    if not _column_exists("discount_codes", "max_uses_per_user"):
        op.add_column(
            "discount_codes",
            sa.Column("max_uses_per_user", sa.Integer(), nullable=False, server_default="1"),
        )

    if not _constraint_exists("discount_usage", "uq_discount_usage_code_user"):
        return

    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        with op.batch_alter_table("discount_usage") as batch_op:
            batch_op.drop_constraint("uq_discount_usage_code_user", type_="unique")
    else:
        op.drop_constraint("uq_discount_usage_code_user", "discount_usage", type_="unique")


def downgrade() -> None:
    pass
