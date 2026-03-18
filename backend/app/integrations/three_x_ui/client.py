from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config.settings import get_settings
from app.core.security import decrypt_secret
from app.integrations.three_x_ui.base import BaseThreeXUIAdapter
from app.integrations.three_x_ui.exceptions import ThreeXUIAuthError, ThreeXUIRequestError
from app.models.server import Server
from app.utils.serialization import dump_json, parse_json_field

logger = logging.getLogger(__name__)


class ThreeXUIAdapter(BaseThreeXUIAdapter):
    def __init__(self, server: Server) -> None:
        self.server = server
        self.settings = get_settings()

    @property
    def base_url(self) -> str:
        return f"{self.server.scheme}://{self.server.host}:{self.server.port}"

    @property
    def panel_path(self) -> str:
        if not self.server.panel_path:
            return ""
        path = self.server.panel_path.strip()
        if not path.startswith("/"):
            path = f"/{path}"
        return path.rstrip("/")

    def _build_url(self, path: str, *, api: bool = True) -> str:
        api_prefix = f"{self.panel_path}/panel/api" if api else self.panel_path
        return f"{self.base_url}{api_prefix}{path}"

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.settings.three_xui_timeout_seconds,
            verify=self.settings.three_xui_verify_ssl,
            follow_redirects=True,
        )

    def _parse_response(self, response: httpx.Response) -> Any:
        if not response.text.strip():
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    def _login(self, client: httpx.Client) -> None:
        payload = {
            "username": self.server.username or "",
            "password": decrypt_secret(self.server.password_encrypted) or "",
        }
        response = client.post(self._build_url("/login", api=False), data=payload)
        if response.status_code >= 400:
            raise ThreeXUIAuthError(f"Ошибка авторизации в 3x-ui: HTTP {response.status_code}")

        data = self._parse_response(response)
        if isinstance(data, dict) and data.get("success") is False:
            raise ThreeXUIAuthError(data.get("msg") or "3x-ui отклонил авторизацию")

    def _request(self, method: str, path: str, *, client: httpx.Client, **kwargs: Any) -> Any:
        response = client.request(method, self._build_url(path), **kwargs)
        if response.status_code >= 400:
            raise ThreeXUIRequestError(f"3x-ui вернул HTTP {response.status_code} для {path}")
        data = self._parse_response(response)
        if isinstance(data, dict) and data.get("success") is False:
            raise ThreeXUIRequestError(data.get("msg") or f"3x-ui отклонил запрос {path}")
        if isinstance(data, dict) and "obj" in data:
            return data["obj"]
        return data

    def _normalize_inbound(self, inbound: dict) -> dict:
        normalized = dict(inbound)
        normalized["settings"] = parse_json_field(normalized.get("settings"))
        normalized["streamSettings"] = parse_json_field(normalized.get("streamSettings"))
        normalized["sniffing"] = parse_json_field(normalized.get("sniffing"))
        return normalized

    def check_connection(self) -> dict:
        with self._build_client() as client:
            self._login(client)
            status = self._request("GET", "/server/status", client=client)
            inbounds = self._request("GET", "/inbounds/list", client=client) or []
            version = None
            if isinstance(status, dict):
                version = status.get("xray", {}).get("version") or status.get("version")
            return {
                "status": status or {},
                "version": version,
                "inbounds": [self._normalize_inbound(item) for item in inbounds if isinstance(item, dict)],
            }

    def list_inbounds(self) -> list[dict]:
        with self._build_client() as client:
            self._login(client)
            payload = self._request("GET", "/inbounds/list", client=client) or []
            return [self._normalize_inbound(item) for item in payload if isinstance(item, dict)]

    def get_inbound(self, inbound_id: int) -> dict:
        with self._build_client() as client:
            self._login(client)
            payload = self._request("GET", f"/inbounds/get/{inbound_id}", client=client) or {}
            return self._normalize_inbound(payload)

    def add_client(self, inbound_id: int, client_payload: dict) -> dict:
        body = {"id": inbound_id, "settings": dump_json({"clients": [client_payload]})}
        with self._build_client() as client:
            self._login(client)
            payload = self._request("POST", "/inbounds/addClient", client=client, json=body)
            if payload == {}:
                inbound = self.get_inbound(inbound_id)
                clients = inbound.get("settings", {}).get("clients", [])
                exists = any(item.get("email") == client_payload["email"] for item in clients)
                if not exists:
                    raise ThreeXUIRequestError("3x-ui вернул пустой ответ и клиент не найден после addClient")
                logger.warning("3x-ui вернул пустой ответ на addClient, клиент подтвержден повторным чтением inbound")
            return client_payload

    def update_client(self, client_id: str, inbound_id: int, client_payload: dict) -> dict:
        body = {"id": inbound_id, "settings": dump_json({"clients": [client_payload]})}
        with self._build_client() as client:
            self._login(client)
            payload = self._request(
                "POST",
                f"/inbounds/updateClient/{client_id}",
                client=client,
                json=body,
            )
            if payload == {}:
                inbound = self.get_inbound(inbound_id)
                clients = inbound.get("settings", {}).get("clients", [])
                exists = any(item.get("id") == client_id for item in clients)
                if not exists:
                    raise ThreeXUIRequestError("3x-ui вернул пустой ответ и клиент не найден после updateClient")
            return client_payload

    def delete_client(self, inbound_id: int, client_id: str) -> None:
        with self._build_client() as client:
            self._login(client)
            self._request("POST", f"/inbounds/{inbound_id}/delClient/{client_id}", client=client)

