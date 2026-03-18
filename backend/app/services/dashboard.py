from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.managed_bot import ManagedBot
from app.models.server import Server
from app.models.telegram_user import TelegramUser
from app.models.vpn_access import VpnAccess
from app.schemas.dashboard import DashboardSummary


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_summary(self) -> DashboardSummary:
        total_bots = self.db.scalar(select(func.count(ManagedBot.id))) or 0
        active_bots = self.db.scalar(select(func.count(ManagedBot.id)).where(ManagedBot.is_active.is_(True))) or 0
        total_servers = self.db.scalar(select(func.count(Server.id))) or 0
        active_servers = self.db.scalar(select(func.count(Server.id)).where(Server.is_active.is_(True))) or 0
        active_clients = (
            self.db.scalar(select(func.count(VpnAccess.id)).where(VpnAccess.status == "active")) or 0
        )
        test_clients = (
            self.db.scalar(
                select(func.count(VpnAccess.id)).where(
                    VpnAccess.status == "active", VpnAccess.access_type == "test"
                )
            )
            or 0
        )
        expired_accesses = (
            self.db.scalar(select(func.count(VpnAccess.id)).where(VpnAccess.status == "expired")) or 0
        )
        total_users = self.db.scalar(select(func.count(TelegramUser.id))) or 0
        return DashboardSummary(
            total_bots=total_bots,
            active_bots=active_bots,
            total_servers=total_servers,
            active_servers=active_servers,
            active_clients=active_clients,
            test_clients=test_clients,
            expired_accesses=expired_accesses,
            total_users=total_users,
        )
