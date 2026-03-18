from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.db.session import get_db
from app.schemas.server import (
    InboundSummary,
    ServerCountryLookupRequest,
    ServerCountryLookupResponse,
    ServerCreate,
    ServerRead,
    ServerTestResult,
    ServerUpdate,
)
from app.services.exceptions import ServiceError
from app.services.servers import ServerService

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=list[ServerRead])
def list_servers(db: Session = Depends(get_db)) -> list[ServerRead]:
    return ServerService(db).list_servers()


@router.post("/", response_model=ServerRead)
def create_server(payload: ServerCreate, db: Session = Depends(get_db), admin=Depends(get_current_admin)) -> ServerRead:
    try:
        return ServerService(db).create_server(payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/lookup-country", response_model=ServerCountryLookupResponse)
def lookup_server_country(
    payload: ServerCountryLookupRequest,
    db: Session = Depends(get_db),
) -> ServerCountryLookupResponse:
    try:
        return ServerService(db).detect_country_by_host(payload.host)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.put("/{server_id}", response_model=ServerRead)
def update_server(
    server_id: str,
    payload: ServerUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> ServerRead:
    try:
        return ServerService(db).update_server(server_id, payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/{server_id}")
def delete_server(server_id: str, db: Session = Depends(get_db), admin=Depends(get_current_admin)) -> dict:
    try:
        ServerService(db).delete_server(server_id, actor_id=str(admin.id))
        return {"message": "Сервер удален"}
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/{server_id}/test", response_model=ServerTestResult)
def test_server(server_id: str, db: Session = Depends(get_db), admin=Depends(get_current_admin)) -> ServerTestResult:
    try:
        return ServerService(db).test_connection(server_id, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{server_id}/inbounds", response_model=list[InboundSummary])
def get_server_inbounds(server_id: str, db: Session = Depends(get_db)) -> list[InboundSummary]:
    try:
        return ServerService(db).list_remote_inbounds(server_id)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
