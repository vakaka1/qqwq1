from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
    site_runtime_token: str = "change-me-site-runtime-token"
    admin_username: str = "admin"
    admin_password: str = "change-me-admin-password"
    allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"
    )
    freekassa_shop_id: int | None = None
    freekassa_api_key: str | None = None
    freekassa_secret_word: str | None = None
    freekassa_secret_word_2: str | None = None
    freekassa_sbp_method_id: int = 44
    freekassa_allowed_ips: str = "168.119.157.136,168.119.60.227,178.154.197.79,51.250.54.238"
    freekassa_require_source_ip_check: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def project_dir(self) -> Path:
        candidate = self.base_dir.parent
        if any(
            (candidate / marker).exists()
            for marker in ("site_templates", "frontend", "docker-compose.yml")
        ):
            return candidate
        return self.base_dir

    @computed_field  # type: ignore[prop-decorator]
    @property
    def static_dir(self) -> Path:
        return self.base_dir / "app" / "static"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def parsed_allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def parsed_freekassa_allowed_ips(self) -> list[str]:
        return [item.strip() for item in self.freekassa_allowed_ips.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
