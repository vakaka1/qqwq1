from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher

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
            except Exception:  # noqa: BLE001
                logger.warning("Не удалось обновить last_synced_at для бота %s", session.config.code)
            await session.dispatcher.start_polling(session.bot)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Polling бота %s завершился ошибкой", session.config.code)
        finally:
            await session.bot.session.close()
            current = self.sessions.get(session.config.code)
            if current is session:
                self.sessions.pop(session.config.code, None)

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
