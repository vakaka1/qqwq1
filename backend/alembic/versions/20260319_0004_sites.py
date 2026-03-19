"""sites

Revision ID: 20260319_0004
Revises: 20260318_0003
Create Date: 2026-03-19 10:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0004"
down_revision = "20260318_0003"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("sites"):
        op.create_table(
            "sites",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("domain", sa.String(length=255), nullable=True),
            sa.Column("public_url", sa.String(length=255), nullable=True),
            sa.Column("template_key", sa.String(length=120), nullable=False),
            sa.Column("server_access_mode", sa.String(length=16), nullable=False, server_default="root"),
            sa.Column("server_host", sa.String(length=255), nullable=False),
            sa.Column("server_port", sa.Integer(), nullable=False, server_default="22"),
            sa.Column("server_username", sa.String(length=128), nullable=False),
            sa.Column("server_password_encrypted", sa.Text(), nullable=False),
            sa.Column("managed_bot_id", sa.String(length=36), nullable=False),
            sa.Column("deployment_status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("ssl_mode", sa.String(length=32), nullable=False, server_default="self-signed"),
            sa.Column("last_deployed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("connection_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("deployment_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["managed_bot_id"], ["managed_bots.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_sites_code"),
        )

    if not _index_exists("sites", "ix_sites_code"):
        op.create_index("ix_sites_code", "sites", ["code"], unique=True)
    if not _index_exists("sites", "ix_sites_name"):
        op.create_index("ix_sites_name", "sites", ["name"])
    if not _index_exists("sites", "ix_sites_domain"):
        op.create_index("ix_sites_domain", "sites", ["domain"])
    if not _index_exists("sites", "ix_sites_managed_bot_id"):
        op.create_index("ix_sites_managed_bot_id", "sites", ["managed_bot_id"])
    if not _index_exists("sites", "ix_sites_deployment_status"):
        op.create_index("ix_sites_deployment_status", "sites", ["deployment_status"])


def downgrade() -> None:
    op.drop_index("ix_sites_deployment_status", table_name="sites")
    op.drop_index("ix_sites_managed_bot_id", table_name="sites")
    op.drop_index("ix_sites_domain", table_name="sites")
    op.drop_index("ix_sites_name", table_name="sites")
    op.drop_index("ix_sites_code", table_name="sites")
    op.drop_table("sites")
