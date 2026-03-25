from __future__ import annotations

import asyncio
import importlib
import sys
from types import SimpleNamespace
from types import ModuleType
from unittest import TestCase
from dataclasses import dataclass


def _install_test_stubs() -> None:
    aiogram_module = ModuleType("aiogram")
    aiogram_module.Bot = object
    aiogram_module.Dispatcher = object
    sys.modules["aiogram"] = aiogram_module

    aiogram_exceptions_module = ModuleType("aiogram.exceptions")

    class TelegramBadRequest(Exception):
        pass

    aiogram_exceptions_module.TelegramBadRequest = TelegramBadRequest
    sys.modules["aiogram.exceptions"] = aiogram_exceptions_module

    aiogram_types_module = ModuleType("aiogram.types")

    class BufferedInputFile:
        def __init__(self, data: bytes, filename: str) -> None:
            self.data = data
            self.filename = filename

    class Update:
        @classmethod
        def model_validate(cls, value):
            return value

    aiogram_types_module.BufferedInputFile = BufferedInputFile
    aiogram_types_module.Update = Update
    sys.modules["aiogram.types"] = aiogram_types_module

    handlers_module = ModuleType("app.handlers.start")
    handlers_module.build_router = lambda client, config: object()
    sys.modules["app.handlers.start"] = handlers_module

    backend_client_module = ModuleType("app.services.backend_client")

    @dataclass(frozen=True)
    class ManagedBotRuntimeConfig:
        id: str
        code: str
        name: str
        product_code: str
        telegram_token: str
        webhook_base_url: str | None = None
        telegram_bot_username: str | None = None
        welcome_text: str | None = None
        help_text: str | None = None

    class BackendClient:
        pass

    backend_client_module.ManagedBotRuntimeConfig = ManagedBotRuntimeConfig
    backend_client_module.BackendClient = BackendClient
    sys.modules["app.services.backend_client"] = backend_client_module


_install_test_stubs()
managed_bot_runner = importlib.import_module("app.services.managed_bot_runner")
ManagedBotRunner = managed_bot_runner.ManagedBotRunner
RunningBotSession = managed_bot_runner.RunningBotSession
ManagedBotRuntimeConfig = sys.modules["app.services.backend_client"].ManagedBotRuntimeConfig


class AwaitableRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    async def __call__(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))


class ManagedBotRunnerWebhookTests(TestCase):
    def test_webhook_session_stays_alive_until_cancelled(self) -> None:
        asyncio.run(self._run_webhook_session_scenario())

    async def _run_webhook_session_scenario(self) -> None:
        mark_bot_synced = AwaitableRecorder()
        client = SimpleNamespace(mark_bot_synced=mark_bot_synced)
        runner = ManagedBotRunner(client=client, sync_interval_seconds=30)
        config = ManagedBotRuntimeConfig(
            id="1",
            code="vpn-pleasebot",
            name="VPN, Please",
            product_code="telegram-config",
            telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
            webhook_base_url="https://example.com/webhooks",
        )
        set_webhook = AwaitableRecorder()
        close_session = AwaitableRecorder()
        bot = SimpleNamespace(
            set_webhook=set_webhook,
            session=SimpleNamespace(close=close_session),
        )
        dispatcher = SimpleNamespace()
        session = RunningBotSession(config=config, bot=bot, dispatcher=dispatcher)
        runner.sessions[config.code] = session

        task = asyncio.create_task(runner._run_session(session))
        session.task = task
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.assertFalse(task.done())
        self.assertEqual(len(mark_bot_synced.calls), 1)
        self.assertEqual(len(set_webhook.calls), 1)
        _, webhook_kwargs = set_webhook.calls[0]
        self.assertEqual(webhook_kwargs["url"], "https://example.com/webhooks/vpn-pleasebot")
        self.assertTrue(webhook_kwargs["drop_pending_updates"])
        self.assertEqual(webhook_kwargs["allowed_updates"], ["message", "callback_query"])

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertNotIn(config.code, runner.sessions)
        self.assertEqual(len(close_session.calls), 1)
