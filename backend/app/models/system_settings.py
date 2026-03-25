from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.models.mixins import TimestampMixin


class SystemSettings(TimestampMixin, Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    app_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    public_app_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    freekassa_public_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trial_duration_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    site_trial_duration_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    site_trial_total_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduler_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    three_xui_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    three_xui_verify_ssl: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bot_webhook_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    freekassa_shop_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    freekassa_sbp_method_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    freekassa_secret_word_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    freekassa_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    freekassa_secret_word_2_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
