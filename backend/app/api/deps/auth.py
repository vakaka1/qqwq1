from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.security import decode_access_token, secure_compare
from app.db.session import get_db
from app.repositories.admin import AdminRepository

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный токен") from exc
    admin = AdminRepository(db).get_by_id(int(payload["sub"]))
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Администратор не найден")
    return admin


def verify_bot_token(x_bot_token: str = Header(..., alias="X-Bot-Token")) -> None:
    if not secure_compare(x_bot_token, settings.bot_backend_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный bot token")


def verify_runner_token(x_runner_token: str = Header(..., alias="X-Runner-Token")) -> None:
    if not secure_compare(x_runner_token, settings.bot_runner_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный runner token")
