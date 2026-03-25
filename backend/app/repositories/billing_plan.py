from __future__ import annotations

from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from app.models.billing_plan import BillingPlan


class BillingPlanRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, plan_id: str) -> BillingPlan | None:
        return self.db.get(BillingPlan, plan_id)

    def list_for_bot(self, managed_bot_id: str, *, active_only: bool = False) -> list[BillingPlan]:
        stmt = (
            select(BillingPlan)
            .where(BillingPlan.managed_bot_id == managed_bot_id)
            .order_by(asc(BillingPlan.sort_order), asc(BillingPlan.duration_hours), asc(BillingPlan.name))
        )
        if active_only:
            stmt = stmt.where(BillingPlan.is_active.is_(True))
        return list(self.db.scalars(stmt))

    def create(self, plan: BillingPlan) -> BillingPlan:
        self.db.add(plan)
        self.db.flush()
        return plan

    def delete(self, plan: BillingPlan) -> None:
        self.db.delete(plan)
        self.db.flush()

