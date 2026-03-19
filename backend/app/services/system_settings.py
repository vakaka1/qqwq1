from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.system_settings import SystemSettings
from app.repositories.system_settings import SystemSettingsRepository
from app.schemas.system_settings import SystemSettingsPayload, SystemSettingsRead
from app.services.audit import AuditService
from app.services.exceptions import ServiceError
from app.services.freekassa import FreeKassaService

DEFAULT_SYSTEM_SETTINGS = {
    "app_name": "Xray Control Center",
    "public_app_url": "http://localhost:8000",
    "trial_duration_hours": 24,
    "site_trial_duration_hours": 6,
    "site_trial_total_gb": 1,
    "scheduler_interval_minutes": 5,
    "three_xui_timeout_seconds": 20,
    "three_xui_verify_ssl": False,
    "bot_webhook_base_url": None,
}


class SystemSettingsService:
    managed_fields = (
        "app_name",
        "public_app_url",
        "trial_duration_hours",
        "site_trial_duration_hours",
        "site_trial_total_gb",
        "scheduler_interval_minutes",
        "three_xui_timeout_seconds",
        "three_xui_verify_ssl",
        "bot_webhook_base_url",
    )

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SystemSettingsRepository(db)
        self.audit = AuditService(db)

    def _build_fallback_values(self) -> dict[str, object]:
        return dict(DEFAULT_SYSTEM_SETTINGS)

    def _build_warnings(self, payload: dict[str, object]) -> list[str]:
        warnings: list[str] = []
        hostname = (urlsplit(str(payload["public_app_url"])).hostname or "").lower()
        if hostname in {"", "localhost", "127.0.0.1", "0.0.0.0"}:
            warnings.append(
                "PUBLIC_APP_URL указывает на localhost. Удаленные сайты и tunnel-runtime не смогут достучаться до админки извне."
            )
        if not bool(payload["three_xui_verify_ssl"]):
            warnings.append("Проверка SSL для 3x-ui отключена. Используйте это только если панель работает с самоподписанным сертификатом.")
        return warnings

    def _build_read(self, record: SystemSettings | None) -> SystemSettingsRead:
        fallback = self._build_fallback_values()
        payload: dict[str, object] = {}
        sources: dict[str, str] = {}
        for field in self.managed_fields:
            stored_value = getattr(record, field) if record else None
            if stored_value is None:
                payload[field] = fallback[field]
                sources[field] = "default"
            else:
                payload[field] = stored_value
                sources[field] = "database"

        return SystemSettingsRead(
            **payload,
            sources=sources,
            warnings=self._build_warnings(payload),
            updated_at=record.updated_at.isoformat() if record and record.updated_at else None,
            freekassa=FreeKassaService().build_public_config(public_app_url=str(payload["public_app_url"])),
        )

    def get_effective(self) -> SystemSettingsRead:
        return self._build_read(self.repo.get())

    def _get_or_create(self) -> SystemSettings:
        record = self.repo.get()
        if record:
            return record
        record = SystemSettings(id=1)
        self.repo.save(record)
        return record

    def update(self, payload: SystemSettingsPayload, actor_id: str | None = None) -> SystemSettingsRead:
        if payload.scheduler_interval_minutes < 1:
            raise ServiceError("Интервал планировщика должен быть больше нуля", 400)

        record = self._get_or_create()
        record.app_name = payload.app_name.strip()
        record.public_app_url = payload.public_app_url.strip().rstrip("/")
        record.trial_duration_hours = payload.trial_duration_hours
        record.site_trial_duration_hours = payload.site_trial_duration_hours
        record.site_trial_total_gb = payload.site_trial_total_gb
        record.scheduler_interval_minutes = payload.scheduler_interval_minutes
        record.three_xui_timeout_seconds = payload.three_xui_timeout_seconds
        record.three_xui_verify_ssl = payload.three_xui_verify_ssl
        record.bot_webhook_base_url = payload.bot_webhook_base_url
        self.repo.save(record)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="system_settings_updated",
            entity_type="system_settings",
            entity_id=str(record.id),
            message="Обновлены системные настройки",
            payload=payload.model_dump(),
        )
        self.db.commit()
        from app.tasks.scheduler import reload_scheduler

        reload_scheduler(payload.scheduler_interval_minutes)
        self.db.refresh(record)
        return self._build_read(record)


def load_effective_system_settings(db: Session | None = None) -> SystemSettingsRead:
    if db is not None:
        return SystemSettingsService(db).get_effective()

    fallback_service = None
    local_db = None
    try:
        local_db = SessionLocal()
        fallback_service = SystemSettingsService(local_db)
        return fallback_service.get_effective()
    except Exception:  # noqa: BLE001
        return SystemSettingsRead(
            app_name=str(DEFAULT_SYSTEM_SETTINGS["app_name"]),
            public_app_url=str(DEFAULT_SYSTEM_SETTINGS["public_app_url"]),
            trial_duration_hours=int(DEFAULT_SYSTEM_SETTINGS["trial_duration_hours"]),
            site_trial_duration_hours=int(DEFAULT_SYSTEM_SETTINGS["site_trial_duration_hours"]),
            site_trial_total_gb=int(DEFAULT_SYSTEM_SETTINGS["site_trial_total_gb"]),
            scheduler_interval_minutes=int(DEFAULT_SYSTEM_SETTINGS["scheduler_interval_minutes"]),
            three_xui_timeout_seconds=int(DEFAULT_SYSTEM_SETTINGS["three_xui_timeout_seconds"]),
            three_xui_verify_ssl=bool(DEFAULT_SYSTEM_SETTINGS["three_xui_verify_ssl"]),
            bot_webhook_base_url=None,
            sources={field: "default" for field in SystemSettingsService.managed_fields},
            warnings=[],
            updated_at=None,
            freekassa=FreeKassaService().build_public_config(
                public_app_url=str(DEFAULT_SYSTEM_SETTINGS["public_app_url"])
            ),
        )
    finally:
        if local_db is not None:
            local_db.close()
