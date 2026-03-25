from __future__ import annotations

from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.mixins import TimestampMixin


class WalletTransaction(TimestampMixin, Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    wallet_id: Mapped[str] = mapped_column(ForeignKey("user_wallets.id"), index=True)
    payment_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id"), nullable=True, index=True)
    billing_plan_id: Mapped[str | None] = mapped_column(ForeignKey("billing_plans.id"), nullable=True, index=True)
    vpn_access_id: Mapped[str | None] = mapped_column(ForeignKey("vpn_accesses.id"), nullable=True, index=True)
    amount_kopecks: Mapped[int] = mapped_column(Integer)
    balance_after_kopecks: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    operation_type: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    wallet = relationship("UserWallet")
    payment = relationship("Payment")
    billing_plan = relationship("BillingPlan")
    vpn_access = relationship("VpnAccess")
