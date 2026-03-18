from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret
from app.models.managed_bot import ManagedBot
from app.repositories.managed_bot import ManagedBotRepository
from app.schemas.managed_bot import (
    ManagedBotCreate,
    ManagedBotRead,
    ManagedBotRuntimeRead,
    ManagedBotUpdate,
)
from app.services.audit import AuditService
from app.services.exceptions import ServiceError
from app.utils.naming import build_unique_slug, slugify_identifier


class ManagedBotService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ManagedBotRepository(db)
        self.audit = AuditService(db)

    def _to_read(self, managed_bot: ManagedBot) -> ManagedBotRead:
        return ManagedBotRead.model_validate(
            {**managed_bot.__dict__, "has_token": bool(managed_bot.telegram_token_encrypted)}
        )

    def list_bots(self) -> list[ManagedBotRead]:
        return [self._to_read(item) for item in self.repo.list()]

    def get_or_404(self, managed_bot_id: str) -> ManagedBot:
        managed_bot = self.repo.get(managed_bot_id)
        if not managed_bot:
            raise ServiceError("Бот не найден", 404)
        return managed_bot

    def get_active_by_code_or_404(self, code: str) -> ManagedBot:
        managed_bot = self.repo.get_by_code(code)
        if not managed_bot or not managed_bot.is_active:
            raise ServiceError("Активный бот не найден", 404)
        return managed_bot

    def _resolve_bot_code(
        self,
        *,
        preferred: str | None,
        name: str,
        username: str | None,
    ) -> str:
        base = slugify_identifier(preferred or username or name, default="bot")
        existing_codes = {item.code for item in self.repo.list() if item.code}
        return build_unique_slug(base, existing_codes)

    def create_bot(self, payload: ManagedBotCreate, actor_id: str | None = None) -> ManagedBotRead:
        managed_bot = ManagedBot(
            code=self._resolve_bot_code(
                preferred=payload.code,
                name=payload.name,
                username=payload.telegram_bot_username,
            ),
            name=payload.name,
            product_code=payload.product_code,
            telegram_token_encrypted=encrypt_secret(payload.telegram_token) or "",
            telegram_bot_username=payload.telegram_bot_username,
            welcome_text=payload.welcome_text,
            help_text=payload.help_text,
            is_active=payload.is_active,
        )
        self.repo.create(managed_bot)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="managed_bot_created",
            entity_type="managed_bot",
            entity_id=managed_bot.id,
            message=f"Создан бот {managed_bot.name}",
            payload={"code": managed_bot.code, "product_code": managed_bot.product_code},
        )
        self.db.commit()
        self.db.refresh(managed_bot)
        return self._to_read(managed_bot)

    def update_bot(
        self, managed_bot_id: str, payload: ManagedBotUpdate, actor_id: str | None = None
    ) -> ManagedBotRead:
        managed_bot = self.get_or_404(managed_bot_id)
        changes = payload.model_dump(exclude_unset=True)
        if "code" in changes and changes["code"] != managed_bot.code:
            existing = self.repo.get_by_code(changes["code"])
            if existing and existing.id != managed_bot.id:
                raise ServiceError("Бот с таким code уже существует", 409)
        token = changes.pop("telegram_token", None)
        for key, value in changes.items():
            setattr(managed_bot, key, value)
        if token is not None:
            managed_bot.telegram_token_encrypted = encrypt_secret(token) or managed_bot.telegram_token_encrypted
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="managed_bot_updated",
            entity_type="managed_bot",
            entity_id=managed_bot.id,
            message=f"Обновлен бот {managed_bot.name}",
            payload={"code": managed_bot.code},
        )
        self.db.commit()
        self.db.refresh(managed_bot)
        return self._to_read(managed_bot)

    def delete_bot(self, managed_bot_id: str, actor_id: str | None = None) -> None:
        managed_bot = self.get_or_404(managed_bot_id)
        self.repo.delete(managed_bot)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="managed_bot_deleted",
            entity_type="managed_bot",
            entity_id=managed_bot.id,
            message=f"Удален бот {managed_bot.name}",
            payload={"code": managed_bot.code},
        )
        self.db.commit()

    def list_runtime_bots(self) -> list[ManagedBotRuntimeRead]:
        result = []
        for item in self.repo.list_active():
            token = decrypt_secret(item.telegram_token_encrypted)
            if not token:
                continue
            result.append(
                ManagedBotRuntimeRead(
                    id=item.id,
                    code=item.code,
                    name=item.name,
                    product_code=item.product_code,
                    telegram_token=token,
                    telegram_bot_username=item.telegram_bot_username,
                    welcome_text=item.welcome_text,
                    help_text=item.help_text,
                )
            )
        return result

    def touch_sync(self, code: str) -> None:
        managed_bot = self.repo.get_by_code(code)
        if not managed_bot:
            return
        managed_bot.last_synced_at = datetime.now(timezone.utc)
        self.db.commit()
