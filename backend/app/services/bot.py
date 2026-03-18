from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.bot import BotStartRequest
from app.schemas.common import MessageResponse
from app.services.managed_bots import ManagedBotService
from app.services.vpn_accesses import VpnAccessService


class BotService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.access_service = VpnAccessService(db)
        self.managed_bots = ManagedBotService(db)

    def handle_start(self, payload: BotStartRequest) -> MessageResponse:
        self.managed_bots.get_active_by_code_or_404(payload.bot_code)
        self.access_service._get_or_create_user(  # noqa: SLF001
            payload.telegram_user_id,
            username=payload.username,
            first_name=payload.first_name,
            last_name=payload.last_name,
            language_code=payload.language_code,
        )
        self.db.commit()
        return MessageResponse(message="Пользователь зарегистрирован")
