from __future__ import annotations

from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from app.models.server import Server


class ServerRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[Server]:
        stmt = select(Server).order_by(asc(Server.name))
        return list(self.db.scalars(stmt))

    def get(self, server_id: str) -> Server | None:
        return self.db.get(Server, server_id)

    def get_by_code(self, code: str) -> Server | None:
        return self.db.scalar(select(Server).where(Server.code == code))

    def create(self, server: Server) -> Server:
        self.db.add(server)
        self.db.flush()
        return server

    def delete(self, server: Server) -> None:
        self.db.delete(server)

    def get_trial_candidates(self, product_code: str) -> list[Server]:
        stmt = (
            select(Server)
            .where(Server.is_active.is_(True), Server.is_trial_enabled.is_(True))
            .order_by(asc(Server.name))
        )

        def supports(server: Server) -> bool:
            capabilities = list(server.capabilities or [])
            if not capabilities or product_code in capabilities:
                return True
            if product_code == "site" and "telegram-config" in capabilities:
                return True
            return False

        return [
            server
            for server in self.db.scalars(stmt)
            if supports(server)
        ]
