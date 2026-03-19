from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.system_settings import SystemSettings


class SystemSettingsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self) -> SystemSettings | None:
        stmt = select(SystemSettings).order_by(SystemSettings.id.asc()).limit(1)
        return self.db.scalar(stmt)

    def save(self, settings: SystemSettings) -> SystemSettings:
        self.db.add(settings)
        self.db.flush()
        return settings
