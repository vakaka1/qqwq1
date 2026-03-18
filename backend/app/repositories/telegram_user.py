from __future__ import annotations

from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from app.models.telegram_user import TelegramUser


class TelegramUserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_telegram_id(self, telegram_user_id: int) -> TelegramUser | None:
        stmt = select(TelegramUser).where(TelegramUser.telegram_user_id == telegram_user_id)
        return self.db.scalar(stmt)

    def list(self) -> list[TelegramUser]:
        stmt = select(TelegramUser).order_by(asc(TelegramUser.registered_at))
        return list(self.db.scalars(stmt))

    def create(self, user: TelegramUser) -> TelegramUser:
        self.db.add(user)
        self.db.flush()
        return user

