"""managed bots

Revision ID: 20260317_0002
Revises: 20260317_0001
Create Date: 2026-03-17 15:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260317_0002"
down_revision = "20260317_0001"
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


def _managed_bot_fk_exists() -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        fk["referred_table"] == "managed_bots" and fk["constrained_columns"] == ["managed_bot_id"]
        for fk in inspector.get_foreign_keys("vpn_accesses")
    )


def upgrade() -> None:
    if not _table_exists("managed_bots"):
        op.create_table(
            "managed_bots",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("product_code", sa.String(length=64), nullable=False, server_default="telegram-config"),
            sa.Column("telegram_token_encrypted", sa.Text(), nullable=False),
            sa.Column("telegram_bot_username", sa.String(length=255), nullable=True),
            sa.Column("welcome_text", sa.Text(), nullable=True),
            sa.Column("help_text", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_managed_bots_code"),
        )
    if not _index_exists("managed_bots", "ix_managed_bots_active"):
        op.create_index("ix_managed_bots_active", "managed_bots", ["is_active"])

    if not _column_exists("vpn_accesses", "managed_bot_id"):
        op.add_column("vpn_accesses", sa.Column("managed_bot_id", sa.String(length=36), nullable=True))

    if not _managed_bot_fk_exists():
        with op.batch_alter_table("vpn_accesses") as batch_op:
            batch_op.create_foreign_key(
                "fk_vpn_accesses_managed_bot_id",
                "managed_bots",
                ["managed_bot_id"],
                ["id"],
            )

    if not _index_exists("vpn_accesses", "ix_vpn_accesses_managed_bot_id"):
        op.create_index("ix_vpn_accesses_managed_bot_id", "vpn_accesses", ["managed_bot_id"])


def downgrade() -> None:
    op.drop_index("ix_vpn_accesses_managed_bot_id", table_name="vpn_accesses")
    op.drop_constraint("fk_vpn_accesses_managed_bot_id", "vpn_accesses", type_="foreignkey")
    op.drop_column("vpn_accesses", "managed_bot_id")
    op.drop_index("ix_managed_bots_active", table_name="managed_bots")
    op.drop_table("managed_bots")
