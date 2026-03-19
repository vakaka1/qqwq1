"""site publish mode

Revision ID: 20260319_0006
Revises: 20260319_0005
Create Date: 2026-03-19 16:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0006"
down_revision = "20260319_0005"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("sites"):
        return

    if not _column_exists("sites", "publish_mode"):
        op.add_column(
            "sites",
            sa.Column("publish_mode", sa.String(length=32), nullable=False, server_default="ip"),
        )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE sites
            SET publish_mode = CASE
                WHEN domain IS NOT NULL AND TRIM(domain) <> '' THEN 'domain'
                ELSE 'ip'
            END
            """
        )
    )

    if not _index_exists("sites", "ix_sites_publish_mode"):
        op.create_index("ix_sites_publish_mode", "sites", ["publish_mode"])


def downgrade() -> None:
    if not _table_exists("sites"):
        return

    if _index_exists("sites", "ix_sites_publish_mode"):
        op.drop_index("ix_sites_publish_mode", table_name="sites")
    if _column_exists("sites", "publish_mode"):
        with op.batch_alter_table("sites") as batch_op:
            batch_op.drop_column("publish_mode")
