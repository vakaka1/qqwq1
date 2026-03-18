from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.audit_log import AuditLogRepository


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditLogRepository(db)

    def log(
        self,
        *,
        actor_type: str,
        event_type: str,
        entity_type: str,
        message: str,
        actor_id: str | None = None,
        entity_id: str | None = None,
        level: str = "info",
        payload: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            level=level,
            message=message,
            payload=payload or {},
        )
        return self.repo.create(entry)

