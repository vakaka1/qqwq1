"""monetization tables

Revision ID: 20260325_0012
Revises: 20260325_0011
Create Date: 2026-03-25 12:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260325_0012"
down_revision = "20260325_0011"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("billing_plans"):
        op.create_table(
            "billing_plans",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("managed_bot_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("duration_hours", sa.Integer(), nullable=False),
            sa.Column("price_kopecks", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["managed_bot_id"], ["managed_bots.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_billing_plans_is_active", "billing_plans", ["is_active"])
        op.create_index("ix_billing_plans_managed_bot_id", "billing_plans", ["managed_bot_id"])

    if not _table_exists("user_wallets"):
        op.create_table(
            "user_wallets",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("telegram_user_id", sa.Integer(), nullable=False),
            sa.Column("managed_bot_id", sa.String(length=36), nullable=False),
            sa.Column("balance_kopecks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("trial_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["managed_bot_id"], ["managed_bots.id"]),
            sa.ForeignKeyConstraint(["telegram_user_id"], ["telegram_users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("telegram_user_id", "managed_bot_id", name="uq_user_wallets_user_bot"),
        )
        op.create_index("ix_user_wallets_managed_bot_id", "user_wallets", ["managed_bot_id"])
        op.create_index("ix_user_wallets_telegram_user_id", "user_wallets", ["telegram_user_id"])

    if not _table_exists("payments"):
        op.create_table(
            "payments",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("merchant_order_id", sa.String(length=64), nullable=False),
            sa.Column("redirect_token", sa.String(length=96), nullable=False),
            sa.Column("telegram_user_id", sa.Integer(), nullable=False),
            sa.Column("managed_bot_id", sa.String(length=36), nullable=False),
            sa.Column("wallet_id", sa.String(length=36), nullable=False),
            sa.Column("billing_plan_id", sa.String(length=36), nullable=True),
            sa.Column("amount_kopecks", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="freekassa"),
            sa.Column("payment_method", sa.String(length=32), nullable=False, server_default="sbp"),
            sa.Column("purpose", sa.String(length=32), nullable=False, server_default="balance_top_up"),
            sa.Column("source_ip", sa.String(length=64), nullable=True),
            sa.Column("payer_email", sa.String(length=255), nullable=True),
            sa.Column("external_order_id", sa.String(length=128), nullable=True),
            sa.Column("external_payment_id", sa.String(length=128), nullable=True),
            sa.Column("provider_payment_url", sa.Text(), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("provider_response", sa.JSON(), nullable=False),
            sa.Column("notification_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["billing_plan_id"], ["billing_plans.id"]),
            sa.ForeignKeyConstraint(["managed_bot_id"], ["managed_bots.id"]),
            sa.ForeignKeyConstraint(["telegram_user_id"], ["telegram_users.id"]),
            sa.ForeignKeyConstraint(["wallet_id"], ["user_wallets.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("merchant_order_id", name="uq_payments_merchant_order_id"),
            sa.UniqueConstraint("redirect_token", name="uq_payments_redirect_token"),
        )
        op.create_index("ix_payments_billing_plan_id", "payments", ["billing_plan_id"])
        op.create_index("ix_payments_managed_bot_id", "payments", ["managed_bot_id"])
        op.create_index("ix_payments_status", "payments", ["status"])
        op.create_index("ix_payments_telegram_user_id", "payments", ["telegram_user_id"])
        op.create_index("ix_payments_wallet_id", "payments", ["wallet_id"])

    if not _table_exists("wallet_transactions"):
        op.create_table(
            "wallet_transactions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("wallet_id", sa.String(length=36), nullable=False),
            sa.Column("payment_id", sa.String(length=36), nullable=True),
            sa.Column("billing_plan_id", sa.String(length=36), nullable=True),
            sa.Column("vpn_access_id", sa.String(length=36), nullable=True),
            sa.Column("amount_kopecks", sa.Integer(), nullable=False),
            sa.Column("balance_after_kopecks", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
            sa.Column("operation_type", sa.String(length=32), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["billing_plan_id"], ["billing_plans.id"]),
            sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
            sa.ForeignKeyConstraint(["vpn_access_id"], ["vpn_accesses.id"]),
            sa.ForeignKeyConstraint(["wallet_id"], ["user_wallets.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_wallet_transactions_billing_plan_id", "wallet_transactions", ["billing_plan_id"])
        op.create_index("ix_wallet_transactions_operation_type", "wallet_transactions", ["operation_type"])
        op.create_index("ix_wallet_transactions_payment_id", "wallet_transactions", ["payment_id"])
        op.create_index("ix_wallet_transactions_vpn_access_id", "wallet_transactions", ["vpn_access_id"])
        op.create_index("ix_wallet_transactions_wallet_id", "wallet_transactions", ["wallet_id"])


def downgrade() -> None:
    if _table_exists("wallet_transactions"):
        op.drop_index("ix_wallet_transactions_wallet_id", table_name="wallet_transactions")
        op.drop_index("ix_wallet_transactions_vpn_access_id", table_name="wallet_transactions")
        op.drop_index("ix_wallet_transactions_payment_id", table_name="wallet_transactions")
        op.drop_index("ix_wallet_transactions_operation_type", table_name="wallet_transactions")
        op.drop_index("ix_wallet_transactions_billing_plan_id", table_name="wallet_transactions")
        op.drop_table("wallet_transactions")

    if _table_exists("payments"):
        op.drop_index("ix_payments_wallet_id", table_name="payments")
        op.drop_index("ix_payments_telegram_user_id", table_name="payments")
        op.drop_index("ix_payments_status", table_name="payments")
        op.drop_index("ix_payments_managed_bot_id", table_name="payments")
        op.drop_index("ix_payments_billing_plan_id", table_name="payments")
        op.drop_table("payments")

    if _table_exists("user_wallets"):
        op.drop_index("ix_user_wallets_telegram_user_id", table_name="user_wallets")
        op.drop_index("ix_user_wallets_managed_bot_id", table_name="user_wallets")
        op.drop_table("user_wallets")

    if _table_exists("billing_plans"):
        op.drop_index("ix_billing_plans_managed_bot_id", table_name="billing_plans")
        op.drop_index("ix_billing_plans_is_active", table_name="billing_plans")
        op.drop_table("billing_plans")
