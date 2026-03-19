from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile

from app.handlers.start import build_router
from app.services.backend_client import BackendClient, ManagedBotRuntimeConfig

logger = logging.getLogger(__name__)


@dataclass
class RunningBotSession:
    config: ManagedBotRuntimeConfig
    bot: Bot
    dispatcher: Dispatcher
    task: asyncio.Task[None] | None = None


class ManagedBotRunner:
    def __init__(self, client: BackendClient, sync_interval_seconds: int) -> None:
        self.client = client
        self.sync_interval_seconds = sync_interval_seconds
        self.sessions: dict[str, RunningBotSession] = {}
        self._stopping = False

    async def _run_session(self, session: RunningBotSession) -> None:
        try:
            try:
                await self.client.mark_bot_synced(session.config.code)
            except Exception: 
                logger.warning("Не удалось обновить last_synced_at для бота %s", session.config.code)
            
            if session.config.webhook_base_url:
                webhook_url = f"{session.config.webhook_base_url.rstrip('/')}/{session.config.code}"
                await session.bot.set_webhook(
                    url=webhook_url,
                    drop_pending_updates=True,
                    allowed_updates=["message", "callback_query"]
                )
                logger.info("Установлен webhook для бота %s: %s", session.config.code, webhook_url)
            else:
                logger.info("Webhook base URL не задан (в системных настройках), запускаю polling для бота %s", session.config.code)
                await session.dispatcher.start_polling(session.bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка при инициализации сессии бота %s", session.config.code)
        finally:
            current = self.sessions.get(session.config.code)
            if current is session:
                self.sessions.pop(session.config.code, None)
            await session.bot.session.close()

    async def feed_update(self, bot_code: str, update_data: dict) -> None:
        session = self.sessions.get(bot_code)
        if not session:
            logger.warning("Обновление для неизвестного бота %s", bot_code)
            return
        
        from aiogram.types import Update
        update = Update.model_validate(update_data)
        await session.dispatcher.feed_update(session.bot, update)

    @staticmethod
    def _is_parse_error(exc: TelegramBadRequest) -> bool:
        return "parse entities" in str(exc).lower()

    @staticmethod
    def _decode_image(image_base64: str | None) -> bytes | None:
        if not image_base64:
            return None
        return base64.b64decode(image_base64)

    @staticmethod
    def _build_photo(
        image_url: str | None,
        image_bytes: bytes | None,
        image_filename: str | None,
    ) -> str | BufferedInputFile:
        if image_url:
            return image_url
        if image_bytes is None:
            raise ValueError("Image payload is missing")
        return BufferedInputFile(image_bytes, filename=image_filename or "mailing-image")

    async def _send_text_message(
        self,
        *,
        bot: Bot,
        chat_id: int,
        text: str,
        parse_mode: str | None,
    ) -> None:
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        except TelegramBadRequest as exc:
            if not parse_mode or not self._is_parse_error(exc):
                raise
            await bot.send_message(chat_id=chat_id, text=text)

    async def _send_photo_message(
        self,
        *,
        bot: Bot,
        chat_id: int,
        text: str,
        image_url: str | None,
        image_bytes: bytes | None,
        image_filename: str | None,
        parse_mode: str | None,
    ) -> None:
        if text and len(text) <= 1024:
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=self._build_photo(image_url, image_bytes, image_filename),
                    caption=text,
                    parse_mode=parse_mode,
                )
                return
            except TelegramBadRequest as exc:
                if not parse_mode or not self._is_parse_error(exc):
                    raise
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=self._build_photo(image_url, image_bytes, image_filename),
                    caption=text,
                )
                return

        await bot.send_photo(
            chat_id=chat_id,
            photo=self._build_photo(image_url, image_bytes, image_filename),
        )
        if text:
            await self._send_text_message(
                bot=bot,
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
            )

    async def _send_to_chat(
        self,
        session: RunningBotSession,
        chat_id: int,
        text: str,
        *,
        image_url: str | None = None,
        image_bytes: bytes | None = None,
        image_filename: str | None = None,
        parse_mode: str | None = "Markdown",
    ) -> bool:
        try:
            if image_url or image_bytes:
                await self._send_photo_message(
                    bot=session.bot,
                    chat_id=chat_id,
                    text=text,
                    image_url=image_url,
                    image_bytes=image_bytes,
                    image_filename=image_filename,
                    parse_mode=parse_mode or None,
                )
            else:
                await self._send_text_message(
                    bot=session.bot,
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode or None,
                )
            return True
        except Exception:
            logger.exception("Не удалось отправить сообщение через бота %s пользователю %s", session.config.code, chat_id)
            return False

    async def send_message(
        self,
        bot_code: str,
        chat_id: int,
        text: str,
        *,
        image_url: str | None = None,
        image_base64: str | None = None,
        image_filename: str | None = None,
        parse_mode: str | None = "Markdown",
    ) -> bool:
        session = self.sessions.get(bot_code)
        if not session:
            logger.warning("Попытка отправить сообщение через неизвестного бота %s", bot_code)
            return False
        try:
            image_bytes = self._decode_image(image_base64)
        except Exception:
            logger.exception("Не удалось декодировать изображение для бота %s", bot_code)
            return False
        return await self._send_to_chat(
            session,
            chat_id,
            text,
            image_url=image_url,
            image_bytes=image_bytes,
            image_filename=image_filename,
            parse_mode=parse_mode,
        )

    async def send_bulk_message(
        self,
        bot_code: str,
        chat_ids: list[int],
        text: str,
        *,
        image_url: str | None = None,
        image_base64: str | None = None,
        image_filename: str | None = None,
        parse_mode: str | None = "Markdown",
    ) -> int:
        session = self.sessions.get(bot_code)
        if not session:
            logger.warning("Попытка массовой отправки через неизвестного бота %s", bot_code)
            return 0
        try:
            image_bytes = self._decode_image(image_base64)
        except Exception:
            logger.exception("Не удалось декодировать изображение для массовой рассылки %s", bot_code)
            return 0

        success_count = 0
        for chat_id in list(dict.fromkeys(chat_ids)):
            if await self._send_to_chat(
                session,
                chat_id,
                text,
                image_url=image_url,
                image_bytes=image_bytes,
                image_filename=image_filename,
                parse_mode=parse_mode,
            ):
                success_count += 1
        return success_count

    async def _start_session(self, config: ManagedBotRuntimeConfig) -> None:
        bot = Bot(config.telegram_token)
        dispatcher = Dispatcher()
        dispatcher.include_router(build_router(self.client, config))
        session = RunningBotSession(config=config, bot=bot, dispatcher=dispatcher)
        task = asyncio.create_task(self._run_session(session), name=f"bot-{config.code}")
        session.task = task
        self.sessions[config.code] = session
        logger.info("Запущен managed bot %s (%s)", config.name, config.code)

    async def _stop_session(self, code: str, reason: str) -> None:
        session = self.sessions.pop(code, None)
        if not session:
            return
        logger.info("Останавливаю managed bot %s: %s", code, reason)
        if session.task is None:
            await session.bot.session.close()
            return
        session.task.cancel()
        try:
            await session.task
        except asyncio.CancelledError:
            pass

    async def sync_once(self) -> None:
        configs = await self.client.list_active_bots()
        incoming = {config.code: config for config in configs}

        for code, session in list(self.sessions.items()):
            target = incoming.pop(code, None)
            if target is None:
                await self._stop_session(code, "бот отключен или удален в backend")
                continue
            if target != session.config:
                await self._stop_session(code, "конфигурация изменена")
                await self._start_session(target)

        for config in incoming.values():
            await self._start_session(config)

    async def run_forever(self) -> None:
        while not self._stopping:
            try:
                await self.sync_once()
            except Exception:  # noqa: BLE001
                logger.exception("Не удалось синхронизировать список managed bots")
            await asyncio.sleep(self.sync_interval_seconds)

    async def shutdown(self) -> None:
        self._stopping = True
        for code in list(self.sessions.keys()):
            await self._stop_session(code, "завершение процесса")
