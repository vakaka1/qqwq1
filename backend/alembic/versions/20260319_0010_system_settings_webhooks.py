"""system settings webhook fields

Revision ID: 20260319_0010
Revises: 20260319_0009
Create Date: 2026-03-19 23:50:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0010"
down_revision = "20260319_0009"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("system_settings", "bot_webhook_base_url"):
        op.add_column("system_settings", sa.Column("bot_webhook_base_url", sa.String(length=255), nullable=True))


def downgrade() -> None:
    if _column_exists("system_settings", "bot_webhook_base_url"):
        with op.batch_alter_table("system_settings") as batch_op:
            batch_op.drop_column("bot_webhook_base_url")
