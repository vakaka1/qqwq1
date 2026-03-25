from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import BaseModel, Field, model_validator

from app.schemas.freekassa import FreeKassaConfigRead


class SystemSettingsPayload(BaseModel):
    app_name: str = Field(min_length=2, max_length=120)
    public_app_url: str = Field(min_length=8, max_length=255)
    freekassa_public_url: str | None = Field(default=None, max_length=255)
    trial_duration_hours: int = Field(ge=1, le=720)
    site_trial_duration_hours: int = Field(ge=1, le=168)
    site_trial_total_gb: int = Field(ge=1, le=100)
    scheduler_interval_minutes: int = Field(ge=1, le=1440)
    three_xui_timeout_seconds: int = Field(ge=1, le=300)
    three_xui_verify_ssl: bool = False
    bot_webhook_base_url: str | None = Field(default=None, max_length=255)
    freekassa_shop_id: int | None = Field(default=None, ge=1)
    freekassa_secret_word: str | None = Field(default=None, max_length=255)
    freekassa_api_key: str | None = Field(default=None, max_length=512)
    freekassa_secret_word_2: str | None = Field(default=None, max_length=255)
    freekassa_sbp_method_id: int = Field(default=42, ge=1, le=999)

    @model_validator(mode="after")
    def validate_urls(self) -> "SystemSettingsPayload":
        # Validate PUBLIC_APP_URL
        parsed = urlsplit(self.public_app_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("PUBLIC_APP_URL должен быть абсолютным http/https URL")
        normalized_path = parsed.path.rstrip("/")
        self.public_app_url = (
            f"{parsed.scheme}://{parsed.netloc}{normalized_path}" if normalized_path else f"{parsed.scheme}://{parsed.netloc}"
        )

        if self.freekassa_public_url:
            parsed_freekassa = urlsplit(self.freekassa_public_url.strip())
            if parsed_freekassa.scheme not in {"http", "https"} or not parsed_freekassa.netloc:
                raise ValueError("freekassa_public_url должен быть абсолютным http/https URL")
            normalized_freekassa_path = parsed_freekassa.path.rstrip("/")
            self.freekassa_public_url = (
                f"{parsed_freekassa.scheme}://{parsed_freekassa.netloc}{normalized_freekassa_path}"
                if normalized_freekassa_path
                else f"{parsed_freekassa.scheme}://{parsed_freekassa.netloc}"
            )

        # Validate bot_webhook_base_url if present
        if self.bot_webhook_base_url:
            parsed_webhook = urlsplit(self.bot_webhook_base_url.strip())
            if parsed_webhook.scheme not in {"http", "https"} or not parsed_webhook.netloc:
                raise ValueError("bot_webhook_base_url должен быть абсолютным http/https URL")
            self.bot_webhook_base_url = self.bot_webhook_base_url.strip().rstrip("/")
        
        return self


class SystemSettingsRead(SystemSettingsPayload):
    sources: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    updated_at: str | None = None
    freekassa: FreeKassaConfigRead | None = None
