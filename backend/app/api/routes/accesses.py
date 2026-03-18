from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.db.session import get_db
from app.schemas.vpn_access import AccessConfigRead, AccessCreateRequest, AccessExtendRequest, AccessRead
from app.services.exceptions import ServiceError
from app.services.vpn_accesses import VpnAccessService

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=list[AccessRead])
def list_accesses(
    server_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    access_type: str | None = Query(default=None),
    telegram_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AccessRead]:
    return VpnAccessService(db).list_accesses(
        server_id=server_id,
        status=status,
        access_type=access_type,
        telegram_user_id=telegram_user_id,
    )


@router.post("/", response_model=AccessRead)
def create_access(
    payload: AccessCreateRequest,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> AccessRead:
    try:
        return VpnAccessService(db).create_manual_access(payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/{access_id}/extend", response_model=AccessRead)
def extend_access(
    access_id: str,
    payload: AccessExtendRequest,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> AccessRead:
    try:
        return VpnAccessService(db).extend_access(access_id, payload.duration_hours, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/{access_id}/disable", response_model=AccessRead)
def disable_access(
    access_id: str,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> AccessRead:
    try:
        return VpnAccessService(db).disable_access(access_id, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/{access_id}")
def delete_access(
    access_id: str,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> dict:
    try:
        VpnAccessService(db).delete_access(access_id, actor_id=str(admin.id))
        return {"message": "Доступ удален"}
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{access_id}/config", response_model=AccessConfigRead)
def get_access_config(access_id: str, db: Session = Depends(get_db)) -> AccessConfigRead:
    try:
        return VpnAccessService(db).get_access_config(access_id)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

