from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.payment import Payment


class PaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, payment_id: str) -> Payment | None:
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.wallet),
                joinedload(Payment.telegram_user),
                joinedload(Payment.managed_bot),
                joinedload(Payment.billing_plan),
            )
            .where(Payment.id == payment_id)
        )
        return self.db.scalar(stmt)

    def get_by_redirect_token(self, redirect_token: str) -> Payment | None:
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.wallet),
                joinedload(Payment.telegram_user),
                joinedload(Payment.managed_bot),
                joinedload(Payment.billing_plan),
            )
            .where(Payment.redirect_token == redirect_token)
        )
        return self.db.scalar(stmt)

    def get_by_merchant_order_id(self, merchant_order_id: str) -> Payment | None:
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.wallet),
                joinedload(Payment.telegram_user),
                joinedload(Payment.managed_bot),
                joinedload(Payment.billing_plan),
            )
            .where(Payment.merchant_order_id == merchant_order_id)
        )
        return self.db.scalar(stmt)

    def create(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.flush()
        return payment

    def count_by_status(self, status: str) -> int:
        stmt = select(func.count(Payment.id)).where(Payment.status == status)
        return int(self.db.scalar(stmt) or 0)

    def total_paid_kopecks(self) -> int:
        stmt = select(func.coalesce(func.sum(Payment.amount_kopecks), 0)).where(Payment.status == "paid")
        return int(self.db.scalar(stmt) or 0)

    def list_recent(self, *, limit: int = 10) -> list[Payment]:
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.wallet),
                joinedload(Payment.telegram_user),
                joinedload(Payment.managed_bot),
                joinedload(Payment.billing_plan),
            )
            .order_by(desc(Payment.created_at))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).unique())

