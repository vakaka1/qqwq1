from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.mixins import TimestampMixin


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    merchant_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    redirect_token: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    telegram_user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"), index=True)
    managed_bot_id: Mapped[str] = mapped_column(ForeignKey("managed_bots.id"), index=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("user_wallets.id"), index=True)
    billing_plan_id: Mapped[str | None] = mapped_column(ForeignKey("billing_plans.id"), nullable=True, index=True)
    amount_kopecks: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    provider: Mapped[str] = mapped_column(String(32), default="freekassa")
    payment_method: Mapped[str] = mapped_column(String(32), default="sbp")
    purpose: Mapped[str] = mapped_column(String(32), default="balance_top_up")
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_payment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_response: Mapped[dict] = mapped_column(JSON, default=dict)
    notification_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    telegram_user = relationship("TelegramUser")
    managed_bot = relationship("ManagedBot")
    wallet = relationship("UserWallet")
    billing_plan = relationship("BillingPlan")

