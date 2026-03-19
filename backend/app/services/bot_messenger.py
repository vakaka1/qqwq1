from __future__ import annotations

import base64
import logging
from collections.abc import Sequence

import httpx

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class BotMessengerService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = "http://bot:8001/internal"
        self.headers = {"X-Runner-Token": self.settings.bot_runner_token}

    @staticmethod
    def _encode_image(image_bytes: bytes | None) -> str | None:
        if not image_bytes:
            return None
        return base64.b64encode(image_bytes).decode("ascii")

    @staticmethod
    def _normalize_chat_ids(chat_ids: Sequence[int]) -> list[int]:
        return list(dict.fromkeys(chat_ids))

    def _build_payload(
        self,
        *,
        bot_code: str,
        text: str,
        image_url: str | None = None,
        image_bytes: bytes | None = None,
        image_filename: str | None = None,
        parse_mode: str | None = "Markdown",
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "bot_code": bot_code,
            "text": text,
        }
        if image_url:
            payload["image_url"] = image_url
        encoded_image = self._encode_image(image_bytes)
        if encoded_image:
            payload["image_base64"] = encoded_image
            if image_filename:
                payload["image_filename"] = image_filename
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        return payload

    async def send_message(
        self,
        bot_code: str,
        chat_id: int,
        text: str,
        *,
        image_url: str | None = None,
        image_bytes: bytes | None = None,
        image_filename: str | None = None,
        parse_mode: str | None = "Markdown",
    ) -> bool:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/send-message",
                    json={
                        **self._build_payload(
                            bot_code=bot_code,
                            text=text,
                            image_url=image_url,
                            image_bytes=image_bytes,
                            image_filename=image_filename,
                            parse_mode=parse_mode,
                        ),
                        "chat_id": chat_id,
                    },
                    headers=self.headers,
                )
                response.raise_for_status()
                return True
            except Exception as exc:
                logger.error("Ошибка при отправке сообщения через Bot Runner: %s", exc)
                return False

    def send_message_sync(
        self,
        bot_code: str,
        chat_id: int,
        text: str,
        *,
        image_url: str | None = None,
        image_bytes: bytes | None = None,
        image_filename: str | None = None,
        parse_mode: str | None = "Markdown",
    ) -> bool:
        with httpx.Client(timeout=30.0) as client:
            try:
                response = client.post(
                    f"{self.base_url}/send-message",
                    json={
                        **self._build_payload(
                            bot_code=bot_code,
                            text=text,
                            image_url=image_url,
                            image_bytes=image_bytes,
                            image_filename=image_filename,
                            parse_mode=parse_mode,
                        ),
                        "chat_id": chat_id,
                    },
                    headers=self.headers,
                )
                response.raise_for_status()
                return True
            except Exception as exc:
                logger.error("Ошибка при отправке сообщения через Bot Runner (sync): %s", exc)
                return False

    def send_bulk_message_sync(
        self,
        bot_code: str,
        chat_ids: Sequence[int],
        text: str,
        *,
        image_url: str | None = None,
        image_bytes: bytes | None = None,
        image_filename: str | None = None,
        parse_mode: str | None = "Markdown",
    ) -> int:
        normalized_chat_ids = self._normalize_chat_ids(chat_ids)
        if not normalized_chat_ids:
            return 0

        with httpx.Client(timeout=120.0) as client:
            try:
                response = client.post(
                    f"{self.base_url}/send-bulk-message",
                    json={
                        **self._build_payload(
                            bot_code=bot_code,
                            text=text,
                            image_url=image_url,
                            image_bytes=image_bytes,
                            image_filename=image_filename,
                            parse_mode=parse_mode,
                        ),
                        "chat_ids": normalized_chat_ids,
                    },
                    headers=self.headers,
                )
                response.raise_for_status()
                payload = response.json()
                return int(payload.get("success_count", 0))
            except Exception as exc:
                logger.error("Ошибка при массовой отправке через Bot Runner (sync): %s", exc)
                return 0
