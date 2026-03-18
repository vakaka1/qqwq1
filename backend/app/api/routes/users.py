from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.db.session import get_db
from app.repositories.telegram_user import TelegramUserRepository
from app.schemas.telegram_user import TelegramUserRead

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=list[TelegramUserRead])
def list_users(db: Session = Depends(get_db)) -> list[TelegramUserRead]:
    users = TelegramUserRepository(db).list()
    return [TelegramUserRead.model_validate(user) for user in users]

