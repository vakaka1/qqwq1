"""add freekassa secret word

Revision ID: 20260325_0015
Revises: 20260325_0014
Create Date: 2026-03-25 20:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260325_0015"
down_revision = "20260325_0014"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("system_settings", "freekassa_secret_word_encrypted"):
        op.add_column("system_settings", sa.Column("freekassa_secret_word_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch_op:
        if _column_exists("system_settings", "freekassa_secret_word_encrypted"):
            batch_op.drop_column("freekassa_secret_word_encrypted")
