from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.mixins import TimestampMixin


class Site(TimestampMixin, Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    publish_mode: Mapped[str] = mapped_column(String(32), default="ip", index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    public_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    template_key: Mapped[str] = mapped_column(String(120))
    server_access_mode: Mapped[str] = mapped_column(String(16), default="root")
    server_host: Mapped[str] = mapped_column(String(255))
    server_port: Mapped[int] = mapped_column(Integer, default=22)
    server_username: Mapped[str] = mapped_column(String(128))
    proxy_port: Mapped[int] = mapped_column(Integer, default=5000)
    server_password_encrypted: Mapped[str] = mapped_column(Text)
    managed_bot_id: Mapped[str] = mapped_column(ForeignKey("managed_bots.id"), index=True)
    deployment_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    ssl_mode: Mapped[str] = mapped_column(String(32), default="self-signed")
    last_deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    connection_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    deployment_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    managed_bot = relationship("ManagedBot", back_populates="sites")
    accesses = relationship("VpnAccess", back_populates="site")
