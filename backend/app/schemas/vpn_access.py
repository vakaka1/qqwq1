from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.managed_bot import ManagedBotRead
from app.schemas.server import ServerRead
from app.schemas.telegram_user import TelegramUserRead


class AccessCreateRequest(BaseModel):
    telegram_user_id: int | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    managed_bot_id: str | None = None
    server_id: str
    access_type: str = "paid"
    duration_hours: int = Field(default=720, ge=1, le=24 * 365)
    product_code: str = "telegram-config"
    device_limit: int = Field(default=1, ge=1, le=10)
    client_flow: str | None = None


class AccessExtendRequest(BaseModel):
    duration_hours: int = Field(ge=1, le=24 * 365)


class AccessConfigRead(BaseModel):
    access_id: str
    config_uri: str
    config_text: str
    expires_at: datetime


class AccessSiteRead(BaseModel):
    id: str
    code: str
    name: str
    domain: str | None = None
    public_url: str | None = None


class AccessRead(ORMModel):
    id: str
    product_code: str
    access_type: str
    protocol: str
    status: str
    inbound_id: int
    client_uuid: str
    client_email: str
    remote_client_id: str
    client_sub_id: str | None
    device_limit: int
    expiry_at: datetime
    activated_at: datetime
    deactivated_at: datetime | None
    config_uri: str | None
    config_text: str | None
    config_metadata: dict
    created_at: datetime
    updated_at: datetime
    server: ServerRead
    managed_bot: ManagedBotRead | None = None
    site: AccessSiteRead | None = None
    telegram_user: TelegramUserRead | None
