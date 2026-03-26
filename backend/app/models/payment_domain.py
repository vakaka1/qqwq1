from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.models.mixins import TimestampMixin


class PaymentDomain(TimestampMixin, Base):
    __tablename__ = "payment_domains"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    public_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    server_access_mode: Mapped[str] = mapped_column(String(16), default="root")
    server_host: Mapped[str] = mapped_column(String(255))
    server_port: Mapped[int] = mapped_column(Integer, default=22)
    server_username: Mapped[str] = mapped_column(String(128))
    server_password_encrypted: Mapped[str] = mapped_column(Text)
    deployment_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    ssl_mode: Mapped[str] = mapped_column(String(32), default="letsencrypt")
    last_deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    connection_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    deployment_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
