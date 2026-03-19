from __future__ import annotations

from uuid import uuid4

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.enums import HealthStatus
from app.models.mixins import TimestampMixin


class Server(TimestampMixin, Base):
    __tablename__ = "servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    country: Mapped[str] = mapped_column(String(64))
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    host: Mapped[str] = mapped_column(String(255))
    public_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheme: Mapped[str] = mapped_column(String(16), default="http")
    port: Mapped[int] = mapped_column(Integer)
    public_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    panel_path: Mapped[str] = mapped_column(String(128), default="")
    connection_type: Mapped[str] = mapped_column(String(32), default="three_x_ui_http")
    auth_mode: Mapped[str] = mapped_column(String(32), default="username_password")
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    inbound_id: Mapped[int] = mapped_column(Integer)
    client_flow: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_trial_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    health_status: Mapped[str] = mapped_column(String(32), default=HealthStatus.UNKNOWN.value)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["telegram-config", "site"])
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    accesses = relationship("VpnAccess", back_populates="server")
