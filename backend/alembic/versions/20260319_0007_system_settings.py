"""system settings

Revision ID: 20260319_0007
Revises: 20260319_0006
Create Date: 2026-03-19 18:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0007"
down_revision = "20260319_0006"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("system_settings"):
        return

    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("app_name", sa.String(length=120), nullable=True),
        sa.Column("public_app_url", sa.String(length=255), nullable=True),
        sa.Column("trial_duration_hours", sa.Integer(), nullable=True),
        sa.Column("scheduler_interval_minutes", sa.Integer(), nullable=True),
        sa.Column("three_xui_timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("three_xui_verify_ssl", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    if _table_exists("system_settings"):
        op.drop_table("system_settings")
