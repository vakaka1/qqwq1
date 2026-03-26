from __future__ import annotations

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from app.models.payment_domain import PaymentDomain


class PaymentDomainRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[PaymentDomain]:
        stmt = select(PaymentDomain).order_by(desc(PaymentDomain.created_at), asc(PaymentDomain.domain))
        return list(self.db.scalars(stmt).unique())

    def get(self, payment_domain_id: str) -> PaymentDomain | None:
        stmt = select(PaymentDomain).where(PaymentDomain.id == payment_domain_id)
        return self.db.scalar(stmt)

    def get_by_domain(self, domain: str) -> PaymentDomain | None:
        stmt = select(PaymentDomain).where(PaymentDomain.domain == domain)
        return self.db.scalar(stmt)

    def create(self, payment_domain: PaymentDomain) -> PaymentDomain:
        self.db.add(payment_domain)
        self.db.flush()
        return payment_domain

    def delete(self, payment_domain: PaymentDomain) -> None:
        self.db.delete(payment_domain)
        self.db.flush()
