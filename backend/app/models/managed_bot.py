from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.mixins import TimestampMixin


class ManagedBot(TimestampMixin, Base):
    __tablename__ = "managed_bots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    product_code: Mapped[str] = mapped_column(String(64), default="telegram-config")
    telegram_token_encrypted: Mapped[str] = mapped_column(Text)
    telegram_bot_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    welcome_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    accesses = relationship("VpnAccess", back_populates="managed_bot")
