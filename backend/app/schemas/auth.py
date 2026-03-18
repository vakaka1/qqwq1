from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str
    password: str


class AdminRead(ORMModel):
    id: int
    username: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    admin: AdminRead


class SetupStatusResponse(BaseModel):
    is_initialized: bool


class InitialSetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=255)
    password_confirm: str = Field(min_length=8, max_length=255)

    @model_validator(mode="after")
    def validate_password_match(self) -> "InitialSetupRequest":
        if self.password != self.password_confirm:
            raise ValueError("Пароли не совпадают")
        return self


class AdminCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=255)
    password_confirm: str = Field(min_length=8, max_length=255)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_password_match(self) -> "AdminCreateRequest":
        if self.password != self.password_confirm:
            raise ValueError("Пароли не совпадают")
        return self


class AdminUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64)
    password: str | None = Field(default=None, min_length=8, max_length=255)
    password_confirm: str | None = Field(default=None, min_length=8, max_length=255)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_password_match(self) -> "AdminUpdateRequest":
        if self.password is None and self.password_confirm is None:
            return self
        if not self.password or not self.password_confirm:
            raise ValueError("Заполните оба поля пароля")
        if self.password != self.password_confirm:
            raise ValueError("Пароли не совпадают")
        return self
