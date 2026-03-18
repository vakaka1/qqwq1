from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.admin import Admin
from app.repositories.admin import AdminRepository
from app.schemas.auth import AdminCreateRequest, AdminRead, AdminUpdateRequest
from app.services.audit import AuditService
from app.services.exceptions import ServiceError


class AdminService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AdminRepository(db)
        self.audit = AuditService(db)

    def _to_read(self, admin: Admin) -> AdminRead:
        return AdminRead.model_validate(admin)

    def list_admins(self) -> list[AdminRead]:
        return [self._to_read(item) for item in self.repo.list()]

    def get_or_404(self, admin_id: int) -> Admin:
        admin = self.repo.get_by_id(admin_id)
        if not admin:
            raise ServiceError("Администратор не найден", 404)
        return admin

    def create_admin(self, payload: AdminCreateRequest, *, actor_id: str | None = None) -> AdminRead:
        if self.repo.get_by_username(payload.username):
            raise ServiceError("Администратор с таким логином уже существует", 409)

        admin = Admin(
            username=payload.username,
            password_hash=hash_password(payload.password),
            is_active=payload.is_active,
        )
        self.repo.create(admin)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="admin_created",
            entity_type="admin",
            entity_id=str(admin.id),
            message=f"Создан администратор {admin.username}",
            payload={"username": admin.username},
        )
        self.db.commit()
        self.db.refresh(admin)
        return self._to_read(admin)

    def update_admin(
        self,
        admin_id: int,
        payload: AdminUpdateRequest,
        *,
        actor_id: str | None = None,
        current_admin_id: int | None = None,
    ) -> AdminRead:
        if current_admin_id is not None and current_admin_id != admin_id:
            raise ServiceError("Нельзя редактировать другую учетную запись администратора", 403)

        admin = self.get_or_404(admin_id)
        changes = payload.model_dump(exclude_unset=True)
        password = changes.pop("password", None)
        changes.pop("password_confirm", None)
        if "username" in changes and changes["username"] != admin.username:
            existing = self.repo.get_by_username(changes["username"])
            if existing and existing.id != admin.id:
                raise ServiceError("Администратор с таким логином уже существует", 409)

        next_is_active = changes.get("is_active", admin.is_active)
        if admin.is_active and not next_is_active and self.repo.count_active() <= 1:
            raise ServiceError("Нельзя отключить последнего активного администратора", 409)
        if current_admin_id == admin.id and admin.is_active and not next_is_active:
            raise ServiceError("Нельзя отключить собственную учетную запись", 409)

        for key, value in changes.items():
            setattr(admin, key, value)
        if password:
            admin.password_hash = hash_password(password)

        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="admin_updated",
            entity_type="admin",
            entity_id=str(admin.id),
            message=f"Обновлен администратор {admin.username}",
            payload={"username": admin.username, "is_active": admin.is_active},
        )
        self.db.commit()
        self.db.refresh(admin)
        return self._to_read(admin)
