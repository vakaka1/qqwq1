from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.db.session import get_db
from app.schemas.managed_bot import ManagedBotCreate, ManagedBotRead, ManagedBotUpdate
from app.services.exceptions import ServiceError
from app.services.managed_bots import ManagedBotService

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=list[ManagedBotRead])
def list_bots(db: Session = Depends(get_db)) -> list[ManagedBotRead]:
    return ManagedBotService(db).list_bots()


@router.post("/", response_model=ManagedBotRead)
def create_bot(
    payload: ManagedBotCreate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> ManagedBotRead:
    try:
        return ManagedBotService(db).create_bot(payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.put("/{managed_bot_id}", response_model=ManagedBotRead)
def update_bot(
    managed_bot_id: str,
    payload: ManagedBotUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> ManagedBotRead:
    try:
        return ManagedBotService(db).update_bot(managed_bot_id, payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/{managed_bot_id}")
def delete_bot(
    managed_bot_id: str,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> dict:
    try:
        ManagedBotService(db).delete_bot(managed_bot_id, actor_id=str(admin.id))
        return {"message": "Бот удален"}
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

