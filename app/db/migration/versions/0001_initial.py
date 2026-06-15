"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-15

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("full_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("referral_code", sa.String(20), nullable=False),
        sa.Column("referred_by", sa.BigInteger(), nullable=True),
        sa.Column("bonus_pending_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_agent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("agent_credit_gb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_trial_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("tg_id"),
        sa.UniqueConstraint("referral_code"),
    )

    op.create_table(
        "vpn_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("panel_email", sa.String(255), nullable=False),
        sa.Column("panel_uuid", sa.String(36), nullable=False),
        sa.Column("subscription_id", sa.String(50), nullable=False),
        sa.Column("subscription_url", sa.Text(), nullable=False),
        sa.Column("traffic_limit_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("traffic_used_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("expiry_date", sa.DateTime(), nullable=True),
        sa.Column("is_trial", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("plan_key", sa.String(50), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("renewed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.tg_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("panel_email"),
    )
    op.create_index("ix_vpn_configs_user_id", "vpn_configs", ["user_id"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config_id", sa.Integer(), nullable=True),
        sa.Column("plan_key", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("payment_receipt", sa.Text(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.tg_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("referrer_id", sa.BigInteger(), nullable=False),
        sa.Column("referred_id", sa.BigInteger(), nullable=False),
        sa.Column("bonus_given", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("bonus_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.tg_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referred_id"),
    )
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"])

    op.create_table(
        "agency_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("admin_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.tg_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agency_requests_user_id", "agency_requests", ["user_id"])

    op.create_table(
        "notification_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("config_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("bucket", sa.String(20), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_logs_user_id", "notification_logs", ["user_id"])


def downgrade() -> None:
    op.drop_table("notification_logs")
    op.drop_table("agency_requests")
    op.drop_table("referrals")
    op.drop_table("transactions")
    op.drop_table("vpn_configs")
    op.drop_table("users")
