from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ManagedBotBase(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=120)
    product_code: str = Field(default="telegram-config", min_length=2, max_length=64)
    telegram_bot_username: str | None = None
    welcome_text: str | None = None
    help_text: str | None = None
    is_active: bool = True


class ManagedBotCreate(ManagedBotBase):
    telegram_token: str = Field(min_length=10)


class ManagedBotUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=64)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    product_code: str | None = Field(default=None, min_length=2, max_length=64)
    telegram_token: str | None = Field(default=None, min_length=10)
    telegram_bot_username: str | None = None
    welcome_text: str | None = None
    help_text: str | None = None
    is_active: bool | None = None


class ManagedBotRead(ORMModel):
    id: str
    code: str
    name: str
    product_code: str
    telegram_bot_username: str | None
    welcome_text: str | None
    help_text: str | None
    is_active: bool
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
    has_token: bool = False


class ManagedBotRuntimeRead(BaseModel):
    id: str
    code: str
    name: str
    product_code: str
    telegram_token: str
    webhook_base_url: str | None = None
    telegram_bot_username: str | None = None
    welcome_text: str | None = None
    help_text: str | None = None


class ManagedBotMassMailing(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    image_url: str | None = Field(default=None, max_length=512)
