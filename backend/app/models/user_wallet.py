from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.mixins import TimestampMixin


class UserWallet(TimestampMixin, Base):
    __tablename__ = "user_wallets"
    __table_args__ = (
        UniqueConstraint("telegram_user_id", "managed_bot_id", name="uq_user_wallets_user_bot"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    telegram_user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    managed_bot_id: Mapped[str] = mapped_column(ForeignKey("managed_bots.id"), index=True)
    balance_kopecks: Mapped[int] = mapped_column(Integer, default=0)
    trial_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    telegram_user = relationship("TelegramUser")
    managed_bot = relationship("ManagedBot")

