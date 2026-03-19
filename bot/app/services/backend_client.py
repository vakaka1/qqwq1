from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings


@dataclass(frozen=True, slots=True)
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
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.backend_base_url.rstrip("/")
        self.bot_token = settings.bot_backend_token
        self.runner_token = settings.bot_runner_token
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=20.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(self, method: str, path: str, *, headers: dict[str, str] | None = None, **kwargs: Any) -> Any:
        response = await self.client.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            detail = (
                response.json().get("detail")
                if response.headers.get("content-type", "").startswith("application/json")
                else response.text
            )
            raise RuntimeError(detail or "Backend API error")
        return response.json()

    async def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/bot/start",
            headers={"X-Bot-Token": self.bot_token},
            json=payload,
        )

    async def request_trial(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/bot/request-trial",
            headers={"X-Bot-Token": self.bot_token},
            json=payload,
        )

    async def get_user(self, telegram_user_id: int, bot_code: str) -> dict[str, Any]:
        query = urlencode({"bot_code": bot_code})
        return await self._request(
            "GET",
            f"/bot/user/{telegram_user_id}?{query}",
            headers={"X-Bot-Token": self.bot_token},
        )

    async def get_config(self, telegram_user_id: int, bot_code: str) -> dict[str, Any]:
        query = urlencode({"bot_code": bot_code})
        return await self._request(
            "GET",
            f"/bot/config/{telegram_user_id}?{query}",
            headers={"X-Bot-Token": self.bot_token},
        )

    async def ping(self) -> dict[str, Any]:
        return await self._request("POST", "/bot/ping", headers={"X-Bot-Token": self.bot_token})

    async def list_active_bots(self) -> list[ManagedBotRuntimeConfig]:
        payload = await self._request(
            "GET",
            "/bot-runtime/active-bots",
            headers={"X-Runner-Token": self.runner_token},
        )
        return [ManagedBotRuntimeConfig(**item) for item in payload]

    async def mark_bot_synced(self, bot_code: str) -> None:
        await self._request(
            "POST",
            f"/bot-runtime/touch/{bot_code}",
            headers={"X-Runner-Token": self.runner_token},
        )
