from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.security import hash_password
from app.models.admin import Admin

logger = logging.getLogger(__name__)


def ensure_initial_admin(db: Session) -> None:
    settings = get_settings()
    existing = db.scalar(select(Admin).where(Admin.username == settings.admin_username))
    if existing:
        return

    admin = Admin(username=settings.admin_username, password_hash=hash_password(settings.admin_password))
    db.add(admin)
    db.commit()
    logger.warning("Создан первоначальный администратор %s", settings.admin_username)

