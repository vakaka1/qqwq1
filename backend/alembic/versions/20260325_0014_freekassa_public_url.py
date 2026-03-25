"""add freekassa public url

Revision ID: 20260325_0014
Revises: 20260325_0013
Create Date: 2026-03-25 19:15:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260325_0014"
down_revision = "20260325_0013"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("system_settings", "freekassa_public_url"):
        op.add_column("system_settings", sa.Column("freekassa_public_url", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch_op:
        if _column_exists("system_settings", "freekassa_public_url"):
            batch_op.drop_column("freekassa_public_url")
