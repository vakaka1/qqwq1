from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.db.session import get_db
from app.schemas.common import MessageResponse
from app.schemas.monetization import BillingPlanCreate, BillingPlanRead, BillingPlanUpdate, MonetizationSummaryRead
from app.services.exceptions import ServiceError
from app.services.monetization import MonetizationService

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/summary", response_model=MonetizationSummaryRead)
def get_summary(db: Session = Depends(get_db)) -> MonetizationSummaryRead:
    return MonetizationService(db).get_summary()


@router.get("/plans", response_model=list[BillingPlanRead])
def list_plans(
    managed_bot_id: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[BillingPlanRead]:
    return MonetizationService(db).list_plans(managed_bot_id=managed_bot_id, active_only=active_only)


@router.post("/plans", response_model=BillingPlanRead)
def create_plan(
    payload: BillingPlanCreate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> BillingPlanRead:
    try:
        return MonetizationService(db).create_plan(payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.put("/plans/{plan_id}", response_model=BillingPlanRead)
def update_plan(
    plan_id: str,
    payload: BillingPlanUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> BillingPlanRead:
    try:
        return MonetizationService(db).update_plan(plan_id, payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/plans/{plan_id}", response_model=MessageResponse)
def delete_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> MessageResponse:
    try:
        MonetizationService(db).delete_plan(plan_id, actor_id=str(admin.id))
        return MessageResponse(message="Тариф удален")
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
