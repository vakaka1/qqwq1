from __future__ import annotations

import ipaddress
import socket
from typing import Any
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret
from app.integrations.three_x_ui.exceptions import ThreeXUIError
from app.integrations.three_x_ui.factory import build_three_x_ui_adapter
from app.models.server import Server
from app.repositories.server import ServerRepository
from app.schemas.server import (
    InboundSummary,
    ServerCountryLookupResponse,
    ServerCreate,
    ServerProbeResult,
    ServerRead,
    ServerTestResult,
    ServerUpdate,
)
from app.services.audit import AuditService
from app.services.exceptions import ServiceError
from app.utils.naming import build_connection_alias, build_unique_slug, slugify_identifier
from app.utils.serialization import parse_json_field


class ServerService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ServerRepository(db)
        self.audit = AuditService(db)

    def _to_read(self, server: Server) -> ServerRead:
        capabilities = server.capabilities or ["telegram-config", "site"]
        return ServerRead.model_validate(
            {
                **server.__dict__,
                "connection_aliases": [
                    build_connection_alias(server.code, capability) for capability in capabilities
                ],
                "has_password": bool(server.password_encrypted),
                "has_token": bool(server.token_encrypted),
            }
        )

    def _to_inbound_summary(self, inbound: dict[str, Any]) -> InboundSummary:
        return InboundSummary(
            id=int(inbound.get("id")),
            remark=inbound.get("remark"),
            protocol=inbound.get("protocol", "unknown"),
            port=inbound.get("port"),
            enabled=inbound.get("enable"),
        )

    def detect_country_by_host(self, host: str) -> ServerCountryLookupResponse:
        normalized_host = host.strip()
        if not normalized_host:
            raise ServiceError("Укажите IP или домен сервера", 400)

        try:
            ipaddress.ip_address(normalized_host)
            resolved_ip = normalized_host
        except ValueError:
            try:
                address_info = socket.getaddrinfo(normalized_host, None, type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise ServiceError("Не удалось определить IP по указанному домену", 400) from exc

            public_ips: list[str] = []
            fallback_ip: str | None = None
            for item in address_info:
                candidate = item[4][0]
                if fallback_ip is None:
                    fallback_ip = candidate
                try:
                    parsed_ip = ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                if parsed_ip.is_global:
                    public_ips.append(candidate)
            resolved_ip = public_ips[0] if public_ips else fallback_ip or normalized_host

        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                response = client.get(
                    f"http://ip-api.com/json/{resolved_ip}",
                    params={"fields": "status,message,country", "lang": "ru"},
                )
        except httpx.HTTPError as exc:
            raise ServiceError("Не удалось определить страну сервера", 502) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ServiceError("Сервис определения страны вернул некорректный ответ", 502) from exc

        if response.status_code >= 400 or payload.get("status") != "success" or not payload.get("country"):
            raise ServiceError(
                payload.get("message") or "Не удалось определить страну сервера",
                502,
            )

        return ServerCountryLookupResponse(
            country=str(payload["country"]).strip(),
            resolved_ip=resolved_ip,
        )

    def _ensure_auth_inputs(self, *, username: str | None, password: str | None) -> None:
        if not username:
            raise ServiceError("Укажите логин 3x-ui", 400)
        if not password:
            raise ServiceError("Укажите пароль 3x-ui", 400)

    def _build_server_instance(
        self,
        *,
        code: str,
        name: str,
        country: str,
        region: str | None,
        host: str,
        public_host: str | None,
        scheme: str,
        port: int,
        public_port: int | None,
        panel_path: str,
        connection_type: str,
        auth_mode: str,
        username: str | None,
        password: str | None,
        token: str | None,
        inbound_id: int | None,
        client_flow: str | None,
        is_active: bool,
        is_trial_enabled: bool,
        weight: int,
        tags: list[str],
        capabilities: list[str],
        notes: str | None,
    ) -> Server:
        self._ensure_auth_inputs(username=username, password=password)
        return Server(
            code=code,
            name=name,
            country=country,
            region=region,
            host=host,
            public_host=public_host,
            scheme=scheme,
            port=port,
            public_port=public_port,
            panel_path=panel_path,
            connection_type=connection_type,
            auth_mode=auth_mode,
            username=username,
            password_encrypted=encrypt_secret(password),
            token_encrypted=encrypt_secret(token),
            inbound_id=inbound_id,
            client_flow=client_flow,
            is_active=is_active,
            is_trial_enabled=is_trial_enabled,
            weight=weight,
            tags=tags,
            capabilities=capabilities,
            notes=notes,
        )

    def _build_server_from_create_payload(self, payload: ServerCreate) -> Server:
        return self._build_server_instance(
            code=payload.code or slugify_identifier(payload.name or payload.host, default="node"),
            name=payload.name,
            country=payload.country,
            region=payload.region,
            host=payload.host,
            public_host=payload.public_host,
            scheme=payload.scheme,
            port=payload.port,
            public_port=payload.public_port,
            panel_path=payload.panel_path,
            connection_type=payload.connection_type,
            auth_mode=payload.auth_mode,
            username=payload.username,
            password=payload.password,
            token=payload.token,
            inbound_id=payload.inbound_id,
            client_flow=payload.client_flow,
            is_active=payload.is_active,
            is_trial_enabled=payload.is_trial_enabled,
            weight=payload.weight,
            tags=payload.tags,
            capabilities=payload.capabilities,
            notes=payload.notes,
        )

    def _resolve_server_code(
        self,
        *,
        preferred: str | None,
        name: str,
        host: str,
        current_server_id: str | None = None,
    ) -> str:
        base = slugify_identifier(preferred or name or host, default="node")
        existing_codes = {
            item.code
            for item in self.repo.list()
            if item.code and (current_server_id is None or item.id != current_server_id)
        }
        return build_unique_slug(base, existing_codes)

    def _pick_inbound(self, inbounds: list[dict[str, Any]], preferred_id: int | None = None) -> dict[str, Any] | None:
        if not inbounds:
            return None
        if preferred_id is not None:
            for inbound in inbounds:
                if int(inbound.get("id", 0)) == preferred_id:
                    return inbound

        def score(item: dict[str, Any]) -> tuple[int, int]:
            protocol = str(item.get("protocol", "")).lower()
            enabled = item.get("enable") is not False
            return (
                1 if protocol == "vless" else 0,
                1 if enabled else 0,
            )

        return sorted(
            inbounds,
            key=lambda item: (score(item)[0], score(item)[1], int(item.get("id", 0))),
            reverse=True,
        )[0]

    def _infer_client_flow(self, inbound: dict[str, Any]) -> str | None:
        settings = parse_json_field(inbound.get("settings"))
        clients = settings.get("clients") or []
        for client in clients:
            flow = client.get("flow")
            if flow:
                return str(flow)

        stream_settings = parse_json_field(inbound.get("streamSettings"))
        if (
            str(inbound.get("protocol", "")).lower() == "vless"
            and stream_settings.get("security") == "reality"
        ):
            return "xtls-rprx-vision"
        return None

    def _probe_server(self, server: Server) -> ServerProbeResult:
        adapter = build_three_x_ui_adapter(server)
        try:
            data = adapter.check_connection()
        except ThreeXUIError as exc:
            raise ServiceError(str(exc), 400) from exc

        inbounds = [item for item in data.get("inbounds", []) if isinstance(item, dict)]
        selected = self._pick_inbound(inbounds, preferred_id=server.inbound_id)
        selected_id = int(selected.get("id")) if selected else None
        selected_remark = selected.get("remark") if selected else None
        recommended_port = (
            server.public_port
            or (selected.get("port") if selected else None)
            or server.port
        )
        return ServerProbeResult(
            ok=True,
            status="healthy",
            message=(
                "Подключение к 3x-ui успешно. Параметры узла определены автоматически."
                if selected
                else "Подключение к 3x-ui успешно, но inbound не найден."
            ),
            version=data.get("version"),
            inbounds=[self._to_inbound_summary(item) for item in inbounds],
            selected_inbound_id=selected_id,
            selected_inbound_remark=selected_remark,
            recommended_public_host=server.public_host or server.host,
            recommended_public_port=int(recommended_port) if recommended_port is not None else None,
            recommended_client_flow=self._infer_client_flow(selected) if selected else None,
        )

    def _apply_probe_defaults(self, server: Server, probe: ServerProbeResult) -> None:
        if server.inbound_id is None:
            server.inbound_id = probe.selected_inbound_id
        if not server.public_host:
            server.public_host = probe.recommended_public_host
        if not server.public_port:
            server.public_port = probe.recommended_public_port
        if not server.client_flow:
            server.client_flow = probe.recommended_client_flow
        if server.inbound_id is None:
            raise ServiceError(
                "Backend не нашел подходящий inbound в 3x-ui. Подготовьте совместимый inbound на сервере и повторите сохранение.",
                409,
            )

    def list_servers(self) -> list[ServerRead]:
        return [self._to_read(server) for server in self.repo.list()]

    def get_server_or_404(self, server_id: str) -> Server:
        server = self.repo.get(server_id)
        if not server:
            raise ServiceError("Сервер не найден", 404)
        return server

    def probe_connection(self, payload: ServerCreate) -> ServerProbeResult:
        server = self._build_server_from_create_payload(payload)
        return self._probe_server(server)

    def create_server(self, payload: ServerCreate, actor_id: str | None = None) -> ServerRead:
        server = self._build_server_from_create_payload(payload)
        server.code = self._resolve_server_code(
            preferred=payload.code,
            name=server.name,
            host=server.host,
        )
        if payload.auto_configure or server.inbound_id is None:
            probe = self._probe_server(server)
            self._apply_probe_defaults(server, probe)
            server.health_status = "healthy"
            server.last_error = None
            server.last_checked_at = datetime.now(timezone.utc)
        self.repo.create(server)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="server_created",
            entity_type="server",
            entity_id=server.id,
            message=f"Добавлен сервер {server.name}",
            payload={"server_id": server.id, "host": server.host},
        )
        self.db.commit()
        self.db.refresh(server)
        return self._to_read(server)

    def update_server(self, server_id: str, payload: ServerUpdate, actor_id: str | None = None) -> ServerRead:
        server = self.get_server_or_404(server_id)
        changes = payload.model_dump(exclude_unset=True)
        auto_configure = changes.pop("auto_configure", False)
        password = changes.pop("password", None)
        token = changes.pop("token", None)
        next_code = changes.pop("code", None)
        for key, value in changes.items():
            setattr(server, key, value)
        if next_code is not None:
            server.code = self._resolve_server_code(
                preferred=next_code,
                name=server.name,
                host=server.host,
                current_server_id=server.id,
            )
        if password is not None:
            server.password_encrypted = encrypt_secret(password)
        if token is not None:
            server.token_encrypted = encrypt_secret(token)
        if auto_configure:
            probe = self._probe_server(server)
            self._apply_probe_defaults(server, probe)
            server.health_status = "healthy"
            server.last_error = None
            server.last_checked_at = datetime.now(timezone.utc)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="server_updated",
            entity_type="server",
            entity_id=server.id,
            message=f"Обновлен сервер {server.name}",
            payload={"server_id": server.id},
        )
        self.db.commit()
        self.db.refresh(server)
        return self._to_read(server)

    def delete_server(self, server_id: str, actor_id: str | None = None) -> None:
        server = self.get_server_or_404(server_id)
        self.repo.delete(server)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="server_deleted",
            entity_type="server",
            entity_id=server.id,
            message=f"Удален сервер {server.name}",
        )
        self.db.commit()

    def list_remote_inbounds(self, server_id: str) -> list[InboundSummary]:
        server = self.get_server_or_404(server_id)
        adapter = build_three_x_ui_adapter(server)
        try:
            inbounds = adapter.list_inbounds()
        except ThreeXUIError as exc:
            raise ServiceError(f"Не удалось получить inbound-ы: {exc}", 400) from exc
        return [self._to_inbound_summary(inbound) for inbound in inbounds]

    def test_connection(self, server_id: str, actor_id: str | None = None) -> ServerProbeResult:
        server = self.get_server_or_404(server_id)
        try:
            result = self._probe_server(server)
            server.health_status = "healthy"
            server.last_error = None
        except ThreeXUIError as exc:
            server.health_status = "error"
            server.last_error = str(exc)
            result = ServerProbeResult(ok=False, status="error", message=str(exc))
            self.audit.log(
                actor_type="admin",
                actor_id=actor_id,
                event_type="server_connection_error",
                entity_type="server",
                entity_id=server.id,
                level="error",
                message=f"Ошибка подключения к серверу {server.name}",
                payload={"error": str(exc)},
            )
        server.last_checked_at = datetime.now(timezone.utc)
        self.db.commit()
        return result

    def get_decrypted_credentials(self, server: Server) -> dict:
        return {
            "username": server.username,
            "password": decrypt_secret(server.password_encrypted),
            "token": decrypt_secret(server.token_encrypted),
        }
