"""site trial settings

Revision ID: 20260319_0008
Revises: 20260319_0007
Create Date: 2026-03-19 20:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0008"
down_revision = "20260319_0007"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("system_settings", "site_trial_duration_hours"):
        op.add_column("system_settings", sa.Column("site_trial_duration_hours", sa.Integer(), nullable=True))
    if not _column_exists("system_settings", "site_trial_total_gb"):
        op.add_column("system_settings", sa.Column("site_trial_total_gb", sa.Integer(), nullable=True))


def downgrade() -> None:
    if _column_exists("system_settings", "site_trial_total_gb") or _column_exists("system_settings", "site_trial_duration_hours"):
        with op.batch_alter_table("system_settings") as batch_op:
            if _column_exists("system_settings", "site_trial_total_gb"):
                batch_op.drop_column("site_trial_total_gb")
            if _column_exists("system_settings", "site_trial_duration_hours"):
                batch_op.drop_column("site_trial_duration_hours")
