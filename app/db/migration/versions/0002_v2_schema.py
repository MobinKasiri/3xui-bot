"""nexoranode v2 — add missing columns to live database

The production database was stamped with 0001_initial before the v2 redesign
rewrote that migration.  This migration surgically adds/removes the columns
that now differ between the old on-disk schema and the new models.

Revision ID: 0002_v2_schema
Revises: 0001_initial
Create Date: 2026-06-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_v2_schema"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _dialect() -> str:
    return op.get_bind().dialect.name


def _col_exists(table: str, column: str) -> bool:
    """Return True if *column* already exists in *table*."""
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


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    if _dialect() == "sqlite":
        result = conn.execute(
            sa.text(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :t"
            ),
            {"t": table},
        )
        return result.scalar() is not None
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
        ),
        {"t": table},
    )
    return result.scalar() is not None


def _drop_col(table: str, col: str) -> None:
    if not _col_exists(table, col):
        return
    if _dialect() == "sqlite":
        # Dev SQLite may carry legacy columns; models ignore them. DROP COLUMN is brittle here.
        return
    op.drop_column(table, col)


def _add_col(table: str, col: sa.Column) -> None:
    if not _col_exists(table, col.name):
        op.add_column(table, col)


def _constraint_exists(name: str) -> bool:
    conn = op.get_bind()
    if _dialect() == "sqlite":
        for table in ("vpn_configs", "transactions", "referrals", "discount_usage"):
            if not _table_exists(table):
                continue
            rows = conn.execute(sa.text(f"PRAGMA index_list({table})")).fetchall()
            if any(row[1] == name for row in rows):
                return True
        return False
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = :n"
        ),
        {"n": name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    # Local SQLite DBs created by the current 0001_initial already match v2 — skip.
    if _dialect() == "sqlite" and _col_exists("vpn_configs", "service_name"):
        return

    # ── users ────────────────────────────────────────────────────────────────
    for col in ("bonus_pending_mb", "is_agent", "agent_credit_gb", "is_trial_used"):
        _drop_col("users", col)

    # ── vpn_configs ──────────────────────────────────────────────────────────
    _add_col(
        "vpn_configs",
        sa.Column("service_name", sa.String(40), nullable=False, server_default="legacy"),
    )
    _add_col(
        "vpn_configs",
        sa.Column("plan_id", sa.String(50), nullable=False, server_default=""),
    )
    _add_col(
        "vpn_configs",
        sa.Column("plan_gb", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_col(
        "vpn_configs",
        sa.Column("plan_days", sa.Integer(), nullable=False, server_default="0"),
    )

    # Copy old plan_key into plan_id if plan_key still exists
    if _col_exists("vpn_configs", "plan_key"):
        op.execute(
            sa.text("UPDATE vpn_configs SET plan_id = plan_key WHERE plan_id = ''")
        )
        _drop_col("vpn_configs", "plan_key")

    for col in ("is_trial", "renewed_at"):
        _drop_col("vpn_configs", col)

    # Make every legacy row's service_name unique (id-suffixed) so the unique
    # constraint can be applied without conflicts.  Pre-launch data only.
    if _dialect() == "postgresql":
        op.execute(
            sa.text(
                "UPDATE vpn_configs "
                "SET service_name = 'legacy' || id::text "
                "WHERE service_name = 'legacy'"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE vpn_configs "
                "SET service_name = 'legacy' || CAST(id AS TEXT) "
                "WHERE service_name = 'legacy'"
            )
        )

    # Unique constraint on (user_id, service_name)
    if not _constraint_exists("uq_vpn_configs_user_service"):
        if _dialect() == "sqlite":
            with op.batch_alter_table("vpn_configs") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_vpn_configs_user_service", ["user_id", "service_name"]
                )
        else:
            op.create_unique_constraint(
                "uq_vpn_configs_user_service", "vpn_configs", ["user_id", "service_name"]
            )

    # ── transactions ─────────────────────────────────────────────────────────
    _add_col(
        "transactions",
        sa.Column("payment_amount", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_col(
        "transactions",
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
    )
    _add_col("transactions", sa.Column("service_name", sa.String(40), nullable=True))
    _add_col("transactions", sa.Column("payment_method", sa.String(20), nullable=True))
    _add_col("transactions", sa.Column("discount_code", sa.String(50), nullable=True))
    _add_col(
        "transactions",
        sa.Column("discount_amount", sa.Integer(), nullable=False, server_default="0"),
    )

    # Rename plan_key → plan_id in transactions
    if _col_exists("transactions", "plan_key") and not _col_exists("transactions", "plan_id"):
        if _dialect() == "sqlite":
            with op.batch_alter_table("transactions") as batch_op:
                batch_op.alter_column("plan_key", new_column_name="plan_id")
        else:
            op.alter_column("transactions", "plan_key", new_column_name="plan_id")
    elif _col_exists("transactions", "plan_key") and _col_exists("transactions", "plan_id"):
        _drop_col("transactions", "plan_key")
    elif not _col_exists("transactions", "plan_id"):
        _add_col("transactions", sa.Column("plan_id", sa.String(50), nullable=True))

    # ── referrals ────────────────────────────────────────────────────────────
    for col in ("bonus_given", "bonus_mb"):
        _drop_col("referrals", col)

    _add_col(
        "referrals",
        sa.Column("purchase_count", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_col(
        "referrals",
        sa.Column("total_bonus_given", sa.Integer(), nullable=False, server_default="0"),
    )
    _add_col(
        "referrals",
        sa.Column("friend_bonus_given", sa.Boolean(), nullable=False, server_default="false"),
    )

    # ── agency_requests ──────────────────────────────────────────────────────
    if _table_exists("agency_requests"):
        try:
            op.drop_index("ix_agency_requests_user_id", table_name="agency_requests")
        except Exception:
            pass
        op.drop_table("agency_requests")

    # ── discount_codes ───────────────────────────────────────────────────────
    if not _table_exists("discount_codes"):
        op.create_table(
            "discount_codes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("code", sa.String(50), nullable=False),
            sa.Column("discount_percent", sa.Integer(), nullable=True),
            sa.Column("discount_amount", sa.Integer(), nullable=True),
            sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.BigInteger(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code"),
        )

    # ── discount_usage ───────────────────────────────────────────────────────
    if not _table_exists("discount_usage"):
        op.create_table(
            "discount_usage",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("code_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column(
                "used_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["code_id"], ["discount_codes.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.tg_id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code_id", "user_id", name="uq_discount_usage_code_user"),
        )
        op.create_index("ix_discount_usage_user_id", "discount_usage", ["user_id"])

    # ── notification_logs ────────────────────────────────────────────────────
    if not _table_exists("notification_logs"):
        op.create_table(
            "notification_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("config_id", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(30), nullable=False),
            sa.Column("bucket", sa.String(20), nullable=False),
            sa.Column(
                "sent_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_notification_logs_user_id", "notification_logs", ["user_id"]
        )


def downgrade() -> None:
    pass
