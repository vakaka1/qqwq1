from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.db.session import get_db
from app.schemas.auth import AdminCreateRequest, AdminRead, AdminUpdateRequest
from app.services.admins import AdminService
from app.services.exceptions import ServiceError

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=list[AdminRead])
def list_admins(db: Session = Depends(get_db)) -> list[AdminRead]:
    return AdminService(db).list_admins()


@router.post("/", response_model=AdminRead)
def create_admin(
    payload: AdminCreateRequest,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> AdminRead:
    try:
        return AdminService(db).create_admin(payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.put("/{admin_id}", response_model=AdminRead)
def update_admin(
    admin_id: int,
    payload: AdminUpdateRequest,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> AdminRead:
    try:
        return AdminService(db).update_admin(
            admin_id,
            payload,
            actor_id=str(admin.id),
            current_admin_id=admin.id,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
