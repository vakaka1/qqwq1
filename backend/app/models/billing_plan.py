from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models.mixins import TimestampMixin


class BillingPlan(TimestampMixin, Base):
    __tablename__ = "billing_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    managed_bot_id: Mapped[str] = mapped_column(ForeignKey("managed_bots.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_hours: Mapped[int] = mapped_column(Integer)
    price_kopecks: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    managed_bot = relationship("ManagedBot")

