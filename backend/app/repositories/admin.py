from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.admin import Admin


class AdminRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_username(self, username: str) -> Admin | None:
        return self.db.scalar(select(Admin).where(Admin.username == username))

    def get_by_id(self, admin_id: int) -> Admin | None:
        return self.db.get(Admin, admin_id)

    def list(self) -> list[Admin]:
        return list(self.db.scalars(select(Admin).order_by(Admin.username.asc())))

    def count(self) -> int:
        return self.db.scalar(select(func.count(Admin.id))) or 0

    def count_active(self) -> int:
        return self.db.scalar(select(func.count(Admin.id)).where(Admin.is_active.is_(True))) or 0

    def create(self, admin: Admin) -> Admin:
        self.db.add(admin)
        self.db.flush()
        return admin
