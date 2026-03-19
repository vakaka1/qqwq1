"""site runtime accesses

Revision ID: 20260319_0005
Revises: 20260319_0004
Create Date: 2026-03-19 12:30:00.000000
"""
from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260319_0005"
down_revision = "20260319_0004"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _vpn_access_fk_exists(column_name: str, referred_table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        fk["referred_table"] == referred_table and fk["constrained_columns"] == [column_name]
        for fk in inspector.get_foreign_keys("vpn_accesses")
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _column_exists("vpn_accesses", "site_id"):
        op.add_column("vpn_accesses", sa.Column("site_id", sa.String(length=36), nullable=True))
    if not _column_exists("vpn_accesses", "site_visitor_token"):
        op.add_column("vpn_accesses", sa.Column("site_visitor_token", sa.String(length=64), nullable=True))

    if not _vpn_access_fk_exists("site_id", "sites"):
        with op.batch_alter_table("vpn_accesses") as batch_op:
            batch_op.create_foreign_key(
                "fk_vpn_accesses_site_id",
                "sites",
                ["site_id"],
                ["id"],
            )

    if not _index_exists("vpn_accesses", "ix_vpn_accesses_site_id"):
        op.create_index("ix_vpn_accesses_site_id", "vpn_accesses", ["site_id"])
    if not _index_exists("vpn_accesses", "ix_vpn_accesses_site_visitor_token"):
        op.create_index("ix_vpn_accesses_site_visitor_token", "vpn_accesses", ["site_visitor_token"])

    rows = bind.execute(sa.text("SELECT id, capabilities FROM servers")).mappings().all()
    for row in rows:
        raw_capabilities = row["capabilities"]
        try:
            capabilities = json.loads(raw_capabilities) if isinstance(raw_capabilities, str) else list(raw_capabilities or [])
        except (TypeError, ValueError):
            capabilities = []
        if "telegram-config" in capabilities and "site" not in capabilities:
            capabilities.append("site")
            bind.execute(
                sa.text("UPDATE servers SET capabilities = :capabilities WHERE id = :server_id"),
                {"capabilities": json.dumps(capabilities), "server_id": row["id"]},
            )


def downgrade() -> None:
    if _index_exists("vpn_accesses", "ix_vpn_accesses_site_visitor_token"):
        op.drop_index("ix_vpn_accesses_site_visitor_token", table_name="vpn_accesses")
    if _index_exists("vpn_accesses", "ix_vpn_accesses_site_id"):
        op.drop_index("ix_vpn_accesses_site_id", table_name="vpn_accesses")
    if _vpn_access_fk_exists("site_id", "sites"):
        with op.batch_alter_table("vpn_accesses") as batch_op:
            batch_op.drop_constraint("fk_vpn_accesses_site_id", type_="foreignkey")
    if _column_exists("vpn_accesses", "site_visitor_token") or _column_exists("vpn_accesses", "site_id"):
        with op.batch_alter_table("vpn_accesses") as batch_op:
            if _column_exists("vpn_accesses", "site_visitor_token"):
                batch_op.drop_column("site_visitor_token")
            if _column_exists("vpn_accesses", "site_id"):
                batch_op.drop_column("site_id")
