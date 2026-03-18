from __future__ import annotations

from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from app.models.managed_bot import ManagedBot


class ManagedBotRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[ManagedBot]:
        stmt = select(ManagedBot).order_by(asc(ManagedBot.name))
        return list(self.db.scalars(stmt))

    def list_active(self) -> list[ManagedBot]:
        stmt = select(ManagedBot).where(ManagedBot.is_active.is_(True)).order_by(asc(ManagedBot.name))
        return list(self.db.scalars(stmt))

    def get(self, managed_bot_id: str) -> ManagedBot | None:
        return self.db.get(ManagedBot, managed_bot_id)

    def get_by_code(self, code: str) -> ManagedBot | None:
        stmt = select(ManagedBot).where(ManagedBot.code == code)
        return self.db.scalar(stmt)

    def create(self, managed_bot: ManagedBot) -> ManagedBot:
        self.db.add(managed_bot)
        self.db.flush()
        return managed_bot

    def delete(self, managed_bot: ManagedBot) -> None:
        self.db.delete(managed_bot)

