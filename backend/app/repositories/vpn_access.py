from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.vpn_access import VpnAccess


class VpnAccessRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, access: VpnAccess) -> VpnAccess:
        self.db.add(access)
        self.db.flush()
        return access

    def get(self, access_id: str) -> VpnAccess | None:
        stmt = (
            select(VpnAccess)
            .options(
                joinedload(VpnAccess.server),
                joinedload(VpnAccess.telegram_user),
                joinedload(VpnAccess.managed_bot),
            )
            .where(VpnAccess.id == access_id)
        )
        return self.db.scalar(stmt)

    def list(
        self,
        *,
        server_id: str | None = None,
        status: str | None = None,
        access_type: str | None = None,
        telegram_user_id: int | None = None,
    ) -> list[VpnAccess]:
        stmt = select(VpnAccess).options(
            joinedload(VpnAccess.server),
            joinedload(VpnAccess.telegram_user),
            joinedload(VpnAccess.managed_bot),
        )
        if server_id:
            stmt = stmt.where(VpnAccess.server_id == server_id)
        if status:
            stmt = stmt.where(VpnAccess.status == status)
        if access_type:
            stmt = stmt.where(VpnAccess.access_type == access_type)
        if telegram_user_id:
            stmt = stmt.join(VpnAccess.telegram_user).where(
                VpnAccess.telegram_user.has(telegram_user_id=telegram_user_id)
            )
        stmt = stmt.order_by(desc(VpnAccess.created_at))
        return list(self.db.scalars(stmt).unique())

    def get_latest_for_telegram_user(self, telegram_user_id: int) -> VpnAccess | None:
        stmt = (
            select(VpnAccess)
            .options(
                joinedload(VpnAccess.server),
                joinedload(VpnAccess.telegram_user),
                joinedload(VpnAccess.managed_bot),
            )
            .join(VpnAccess.telegram_user)
            .where(VpnAccess.telegram_user.has(telegram_user_id=telegram_user_id))
            .order_by(desc(VpnAccess.created_at))
            .limit(1)
        )
        return self.db.scalar(stmt)

    def get_latest_for_telegram_user_and_bot(self, telegram_user_id: int, managed_bot_id: str) -> VpnAccess | None:
        stmt = (
            select(VpnAccess)
            .options(
                joinedload(VpnAccess.server),
                joinedload(VpnAccess.telegram_user),
                joinedload(VpnAccess.managed_bot),
            )
            .join(VpnAccess.telegram_user)
            .where(
                VpnAccess.telegram_user.has(telegram_user_id=telegram_user_id),
                VpnAccess.managed_bot_id == managed_bot_id,
                VpnAccess.status != "deleted",
            )
            .order_by(desc(VpnAccess.created_at))
            .limit(1)
        )
        return self.db.scalar(stmt)

    def get_latest_active_for_telegram_user(self, telegram_user_id: int) -> VpnAccess | None:
        stmt = (
            select(VpnAccess)
            .options(
                joinedload(VpnAccess.server),
                joinedload(VpnAccess.telegram_user),
                joinedload(VpnAccess.managed_bot),
            )
            .join(VpnAccess.telegram_user)
            .where(
                VpnAccess.telegram_user.has(telegram_user_id=telegram_user_id),
                VpnAccess.status == "active",
            )
            .order_by(desc(VpnAccess.created_at))
            .limit(1)
        )
        return self.db.scalar(stmt)

    def get_latest_active_for_telegram_user_and_bot(self, telegram_user_id: int, managed_bot_id: str) -> VpnAccess | None:
        stmt = (
            select(VpnAccess)
            .options(
                joinedload(VpnAccess.server),
                joinedload(VpnAccess.telegram_user),
                joinedload(VpnAccess.managed_bot),
            )
            .join(VpnAccess.telegram_user)
            .where(
                VpnAccess.telegram_user.has(telegram_user_id=telegram_user_id),
                VpnAccess.status == "active",
                VpnAccess.managed_bot_id == managed_bot_id,
            )
            .order_by(desc(VpnAccess.created_at))
            .limit(1)
        )
        return self.db.scalar(stmt)

    def get_latest_trial_for_telegram_user_and_bot(self, telegram_user_id: int, managed_bot_id: str) -> VpnAccess | None:
        stmt = (
            select(VpnAccess)
            .options(
                joinedload(VpnAccess.server),
                joinedload(VpnAccess.telegram_user),
                joinedload(VpnAccess.managed_bot),
            )
            .join(VpnAccess.telegram_user)
            .where(
                VpnAccess.telegram_user.has(telegram_user_id=telegram_user_id),
                VpnAccess.access_type == "test",
                VpnAccess.managed_bot_id == managed_bot_id,
                VpnAccess.status != "deleted",
            )
            .order_by(desc(VpnAccess.created_at))
            .limit(1)
        )
        return self.db.scalar(stmt)

    def list_expired_active(self, now: datetime) -> list[VpnAccess]:
        stmt = (
            select(VpnAccess)
            .options(
                joinedload(VpnAccess.server),
                joinedload(VpnAccess.telegram_user),
                joinedload(VpnAccess.managed_bot),
            )
            .where(VpnAccess.status == "active", VpnAccess.expiry_at <= now)
        )
        return list(self.db.scalars(stmt).unique())

    def has_trial_for_user_and_bot(self, internal_user_id: int, managed_bot_id: str) -> bool:
        stmt = select(func.count(VpnAccess.id)).where(
            VpnAccess.telegram_user_id == internal_user_id,
            VpnAccess.access_type == "test",
            VpnAccess.managed_bot_id == managed_bot_id,
            VpnAccess.status != "deleted",
        )
        return bool(self.db.scalar(stmt))
