from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.admin import Admin
from app.repositories.admin import AdminRepository
from app.schemas.auth import TokenResponse
from app.services.exceptions import ServiceError


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AdminRepository(db)

    def is_initialized(self) -> bool:
        return self.repo.count() > 0

    def login(self, username: str, password: str) -> TokenResponse:
        if not self.is_initialized():
            raise ServiceError("Первичная настройка еще не завершена", 409)
        admin = self.repo.get_by_username(username)
        if not admin or not verify_password(password, admin.password_hash):
            raise ServiceError("Неверный логин или пароль", 401)
        if not admin.is_active:
            raise ServiceError("Администратор отключен", 403)

        admin.last_login_at = datetime.now(timezone.utc)
        token, expires_at = create_access_token(str(admin.id))
        self.db.commit()
        return TokenResponse(access_token=token, expires_at=expires_at, admin=admin)

    def create_initial_admin(self, username: str, password: str) -> TokenResponse:
        if self.is_initialized():
            raise ServiceError("Первичная настройка уже завершена", 409)
        if self.repo.get_by_username(username):
            raise ServiceError("Пользователь с таким логином уже существует", 409)

        admin = Admin(username=username, password_hash=hash_password(password))
        self.repo.create(admin)
        self.db.commit()
        self.db.refresh(admin)

        token, expires_at = create_access_token(str(admin.id))
        return TokenResponse(access_token=token, expires_at=expires_at, admin=admin)
