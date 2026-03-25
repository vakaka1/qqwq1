"""system settings freekassa ui fields

Revision ID: 20260325_0013
Revises: 20260325_0012
Create Date: 2026-03-25 16:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260325_0013"
down_revision = "20260325_0012"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("system_settings", "freekassa_shop_id"):
        op.add_column("system_settings", sa.Column("freekassa_shop_id", sa.Integer(), nullable=True))
    if not _column_exists("system_settings", "freekassa_sbp_method_id"):
        op.add_column("system_settings", sa.Column("freekassa_sbp_method_id", sa.Integer(), nullable=True))
    if not _column_exists("system_settings", "freekassa_api_key_encrypted"):
        op.add_column("system_settings", sa.Column("freekassa_api_key_encrypted", sa.Text(), nullable=True))
    if not _column_exists("system_settings", "freekassa_secret_word_2_encrypted"):
        op.add_column("system_settings", sa.Column("freekassa_secret_word_2_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch_op:
        if _column_exists("system_settings", "freekassa_secret_word_2_encrypted"):
            batch_op.drop_column("freekassa_secret_word_2_encrypted")
        if _column_exists("system_settings", "freekassa_api_key_encrypted"):
            batch_op.drop_column("freekassa_api_key_encrypted")
        if _column_exists("system_settings", "freekassa_sbp_method_id"):
            batch_op.drop_column("freekassa_sbp_method_id")
        if _column_exists("system_settings", "freekassa_shop_id"):
            batch_op.drop_column("freekassa_shop_id")
