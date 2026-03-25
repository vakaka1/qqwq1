from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class BotUser(Base):
    __tablename__ = "bot_users"

    telegram_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("telegram_users.id"), primary_key=True)
    managed_bot_id: Mapped[str] = mapped_column(String(36), ForeignKey("managed_bots.id"), primary_key=True)
