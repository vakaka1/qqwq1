from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_backend_token: str = "change-me-bot-backend-token"
    bot_runner_token: str = "change-me-bot-runner-token"
    backend_base_url: str = "http://localhost:8000/api/v1"
    sync_interval_seconds: int = 60


@lru_cache
def get_settings() -> BotSettings:
    return BotSettings()
