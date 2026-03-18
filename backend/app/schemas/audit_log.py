from __future__ import annotations

from datetime import datetime

from app.schemas.common import ORMModel


class AuditLogRead(ORMModel):
    id: int
    actor_type: str
    actor_id: str | None
    event_type: str
    entity_type: str
    entity_id: str | None
    level: str
    message: str
    payload: dict
    created_at: datetime

