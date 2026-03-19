from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.mixins import TimestampMixin, utcnow


class VpnAccess(TimestampMixin, Base):
    __tablename__ = "vpn_accesses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    telegram_user_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_users.id"), nullable=True)
    managed_bot_id: Mapped[str | None] = mapped_column(ForeignKey("managed_bots.id"), nullable=True, index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("sites.id"), nullable=True, index=True)
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id"), index=True)
    product_code: Mapped[str] = mapped_column(String(64), default="telegram-config", index=True)
    access_type: Mapped[str] = mapped_column(String(16))
    protocol: Mapped[str] = mapped_column(String(16), default="vless")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    inbound_id: Mapped[int] = mapped_column(Integer)
    client_uuid: Mapped[str] = mapped_column(String(64))
    client_email: Mapped[str] = mapped_column(String(255), unique=True)
    remote_client_id: Mapped[str] = mapped_column(String(255))
    client_sub_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    site_visitor_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    device_limit: Mapped[int] = mapped_column(Integer, default=1)
    expiry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    telegram_user = relationship("TelegramUser", back_populates="accesses")
    managed_bot = relationship("ManagedBot", back_populates="accesses")
    site = relationship("Site", back_populates="accesses")
    server = relationship("Server", back_populates="accesses")
