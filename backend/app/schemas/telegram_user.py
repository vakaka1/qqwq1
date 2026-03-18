from __future__ import annotations

from datetime import datetime

from app.schemas.common import ORMModel


class TelegramUserRead(ORMModel):
    id: int
    telegram_user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    status: str
    trial_used: bool
    trial_started_at: datetime | None
    trial_ends_at: datetime | None
    registered_at: datetime
    created_at: datetime
    updated_at: datetime

