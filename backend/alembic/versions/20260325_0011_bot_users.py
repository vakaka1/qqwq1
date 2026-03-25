"""bot users link table

Revision ID: 20260325_0011
Revises: 20260319_0010
Create Date: 2026-03-25 09:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260325_0011"
down_revision = "20260319_0010"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("bot_users"):
        return

    op.create_table(
        "bot_users",
        sa.Column("telegram_user_id", sa.Integer(), nullable=False),
        sa.Column("managed_bot_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["telegram_user_id"], ["telegram_users.id"]),
        sa.ForeignKeyConstraint(["managed_bot_id"], ["managed_bots.id"]),
        sa.PrimaryKeyConstraint("telegram_user_id", "managed_bot_id"),
    )


def downgrade() -> None:
    if _table_exists("bot_users"):
        op.drop_table("bot_users")
