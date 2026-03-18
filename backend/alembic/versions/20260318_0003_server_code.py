"""server code

Revision ID: 20260318_0003
Revises: 20260317_0002
Create Date: 2026-03-18 00:30:00.000000
"""
from __future__ import annotations

import re
import unicodedata

from alembic import op
import sqlalchemy as sa


revision = "20260318_0003"
down_revision = "20260317_0002"
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


def _slugify(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_value = re.sub(r"[^a-z0-9]+", "-", ascii_value)
    ascii_value = re.sub(r"-{2,}", "-", ascii_value).strip("-")
    return (ascii_value or "node")[:40].rstrip("-") or "node"


def upgrade() -> None:
    bind = op.get_bind()

    if not _column_exists("servers", "code"):
        op.add_column("servers", sa.Column("code", sa.String(length=64), nullable=True))

    rows = bind.execute(sa.text("SELECT id, name, host, code FROM servers")).mappings().all()
    used_codes: set[str] = set()
    for row in rows:
        current_code = row["code"]
        base = _slugify(current_code or row["name"] or row["host"])
        candidate = base
        suffix = 2
        while candidate in used_codes:
            next_suffix = f"-{suffix}"
            candidate = f"{base[: max(1, 40 - len(next_suffix))].rstrip('-')}{next_suffix}"
            suffix += 1
        used_codes.add(candidate)
        bind.execute(
            sa.text("UPDATE servers SET code = :code WHERE id = :server_id"),
            {"code": candidate, "server_id": row["id"]},
        )

    if not _index_exists("servers", "ix_servers_code"):
        op.create_index("ix_servers_code", "servers", ["code"], unique=True)


def downgrade() -> None:
    if _index_exists("servers", "ix_servers_code"):
        op.drop_index("ix_servers_code", table_name="servers")
    if _column_exists("servers", "code"):
        op.drop_column("servers", "code")
