"""site proxy port

Revision ID: 20260319_0009
Revises: 20260319_0008
Create Date: 2026-03-19 23:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0009"
down_revision = "20260319_0008"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("sites", "proxy_port"):
        op.add_column("sites", sa.Column("proxy_port", sa.Integer(), nullable=True))
    op.execute("UPDATE sites SET proxy_port = 5000 WHERE proxy_port IS NULL")


def downgrade() -> None:
    if _column_exists("sites", "proxy_port"):
        with op.batch_alter_table("sites") as batch_op:
            batch_op.drop_column("proxy_port")
