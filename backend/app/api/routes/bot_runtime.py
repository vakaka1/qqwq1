from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps.auth import verify_runner_token
from app.db.session import get_db
from app.schemas.managed_bot import ManagedBotRuntimeRead
from app.services.managed_bots import ManagedBotService

router = APIRouter(dependencies=[Depends(verify_runner_token)])


@router.get("/active-bots", response_model=list[ManagedBotRuntimeRead])
def active_bots(db: Session = Depends(get_db)) -> list[ManagedBotRuntimeRead]:
    return ManagedBotService(db).list_runtime_bots()


@router.post("/touch/{bot_code}")
def touch_bot(bot_code: str, db: Session = Depends(get_db)) -> dict:
    ManagedBotService(db).touch_sync(bot_code)
    return {"message": "ok"}
