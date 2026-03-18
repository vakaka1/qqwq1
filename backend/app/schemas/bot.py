from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BotStartRequest(BaseModel):
    bot_code: str
    telegram_user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None


class BotUserRead(BaseModel):
    bot_code: str
    telegram_user_id: int
    username: str | None
    status: str
    trial_used: bool
    trial_started_at: datetime | None
    trial_ends_at: datetime | None
    active_access_id: str | None = None
    active_access_status: str | None = None
    active_access_expires_at: datetime | None = None
    server_name: str | None = None


class BotTrialResponse(BaseModel):
    message: str
    bot_code: str
    access_id: str
    config_uri: str
    config_text: str
    expires_at: datetime
    server_name: str


class BotPingResponse(BaseModel):
    status: str
    service: str
