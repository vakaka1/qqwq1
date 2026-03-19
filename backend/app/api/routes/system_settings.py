from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.db.session import get_db
from app.schemas.system_settings import SystemSettingsPayload, SystemSettingsRead
from app.services.exceptions import ServiceError
from app.services.system_settings import SystemSettingsService

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=SystemSettingsRead)
def get_system_settings(db: Session = Depends(get_db)) -> SystemSettingsRead:
    return SystemSettingsService(db).get_effective()


@router.put("/", response_model=SystemSettingsRead)
def update_system_settings(
    payload: SystemSettingsPayload,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> SystemSettingsRead:
    try:
        return SystemSettingsService(db).update(payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
