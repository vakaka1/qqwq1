"""initial schema

Revision ID: 20260317_0001
Revises:
Create Date: 2026-03-17 14:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260317_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_admins_username"),
    )
    op.create_table(
        "servers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=False),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("public_host", sa.String(length=255), nullable=True),
        sa.Column("scheme", sa.String(length=16), nullable=False, server_default="http"),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("public_port", sa.Integer(), nullable=True),
        sa.Column("panel_path", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("connection_type", sa.String(length=32), nullable=False, server_default="three_x_ui_http"),
        sa.Column("auth_mode", sa.String(length=32), nullable=False, server_default="username_password"),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("token_encrypted", sa.Text(), nullable=True),
        sa.Column("inbound_id", sa.Integer(), nullable=False),
        sa.Column("client_flow", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_trial_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("health_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_servers_name", "servers", ["name"])
    op.create_index("ix_servers_trial_active", "servers", ["is_active", "is_trial_enabled"])

    op.create_table(
        "telegram_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("trial_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", name="uq_telegram_users_telegram_user_id"),
    )
    op.create_index("ix_telegram_users_status", "telegram_users", ["status"])

    op.create_table(
        "vpn_accesses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("server_id", sa.String(length=36), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False, server_default="telegram-config"),
        sa.Column("access_type", sa.String(length=16), nullable=False),
        sa.Column("protocol", sa.String(length=16), nullable=False, server_default="vless"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("inbound_id", sa.Integer(), nullable=False),
        sa.Column("client_uuid", sa.String(length=64), nullable=False),
        sa.Column("client_email", sa.String(length=255), nullable=False),
        sa.Column("remote_client_id", sa.String(length=255), nullable=False),
        sa.Column("client_sub_id", sa.String(length=64), nullable=True),
        sa.Column("device_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expiry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_uri", sa.Text(), nullable=True),
        sa.Column("config_text", sa.Text(), nullable=True),
        sa.Column("config_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["server_id"], ["servers.id"]),
        sa.ForeignKeyConstraint(["telegram_user_id"], ["telegram_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_email", name="uq_vpn_accesses_client_email"),
    )
    op.create_index("ix_vpn_accesses_status_expiry", "vpn_accesses", ["status", "expiry_at"])
    op.create_index("ix_vpn_accesses_server_id", "vpn_accesses", ["server_id"])
    op.create_index("ix_vpn_accesses_product_code", "vpn_accesses", ["product_code"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_event_entity", "audit_logs", ["event_type", "entity_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_event_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_vpn_accesses_product_code", table_name="vpn_accesses")
    op.drop_index("ix_vpn_accesses_server_id", table_name="vpn_accesses")
    op.drop_index("ix_vpn_accesses_status_expiry", table_name="vpn_accesses")
    op.drop_table("vpn_accesses")
    op.drop_index("ix_telegram_users_status", table_name="telegram_users")
    op.drop_table("telegram_users")
    op.drop_index("ix_servers_trial_active", table_name="servers")
    op.drop_index("ix_servers_name", table_name="servers")
    op.drop_table("servers")
    op.drop_table("admins")

