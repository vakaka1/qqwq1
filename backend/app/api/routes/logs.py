from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.db.session import get_db
from app.repositories.audit_log import AuditLogRepository
from app.schemas.audit_log import AuditLogRead

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=list[AuditLogRead])
def list_logs(limit: int = Query(default=200, ge=1, le=1000), db: Session = Depends(get_db)) -> list[AuditLogRead]:
    logs = AuditLogRepository(db).list_recent(limit)
    return [AuditLogRead.model_validate(log) for log in logs]

