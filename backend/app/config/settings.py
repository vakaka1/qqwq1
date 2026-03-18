from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Workspace"
    app_env: str = "development"
    debug: bool = False
    auto_create_tables: bool = True
    bootstrap_admin_on_startup: bool = False
    database_url: str = "sqlite:///./backend/data/app.db"
    api_v1_prefix: str = "/api/v1"
    jwt_secret_key: str = "change-me-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    app_encryption_key: str = "change-me-encryption-secret"
    bot_backend_token: str = "change-me-bot-backend-token"
    bot_runner_token: str = "change-me-bot-runner-token"
    admin_username: str = "admin"
    admin_password: str = "change-me-admin-password"
    trial_duration_hours: int = 24
    scheduler_interval_minutes: int = 5
    three_xui_timeout_seconds: int = 20
    three_xui_verify_ssl: bool = False
    allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"
    )
    public_app_url: str = "http://localhost:8000"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def project_dir(self) -> Path:
        return self.base_dir.parent

    @computed_field  # type: ignore[prop-decorator]
    @property
    def static_dir(self) -> Path:
        return self.base_dir / "app" / "static"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def parsed_allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
