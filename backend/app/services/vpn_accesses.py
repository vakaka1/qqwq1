from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from random import choices
from uuid import uuid4

from sqlalchemy.orm import Session

from app.integrations.three_x_ui.exceptions import ThreeXUIError
from app.integrations.three_x_ui.factory import build_three_x_ui_adapter
from app.models.enums import AccessStatus, AccessType, UserStatus
from app.models.managed_bot import ManagedBot
from app.models.server import Server
from app.models.site import Site
from app.models.telegram_user import TelegramUser
from app.models.vpn_access import VpnAccess
from app.repositories.managed_bot import ManagedBotRepository
from app.repositories.server import ServerRepository
from app.repositories.site import SiteRepository
from app.repositories.telegram_user import TelegramUserRepository
from app.repositories.user_wallet import UserWalletRepository
from app.repositories.vpn_access import VpnAccessRepository
from app.schemas.bot import BotTrialResponse, BotUserRead
from app.schemas.site import SiteRuntimeConfigResponse
from app.schemas.vpn_access import AccessConfigRead, AccessCreateRequest, AccessRead
from app.services.audit import AuditService
from app.services.bot_messenger import BotMessengerService
from app.services.config_generator import ConfigGenerator
from app.services.exceptions import ServiceError
from app.services.system_settings import load_effective_system_settings
from app.utils.naming import build_connection_alias, slugify_identifier
from app.utils.serialization import datetime_to_millis, parse_json_field


class VpnAccessService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = TelegramUserRepository(db)
        self.managed_bots = ManagedBotRepository(db)
        self.servers = ServerRepository(db)
        self.sites = SiteRepository(db)
        self.accesses = VpnAccessRepository(db)
        self.wallets = UserWalletRepository(db)
        self.audit = AuditService(db)
        self.generator = ConfigGenerator()
        self.bot_messenger = BotMessengerService()

    def _trial_duration_hours(self) -> int:
        return load_effective_system_settings(self.db).trial_duration_hours

    def _site_trial_duration_hours(self) -> int:
        return load_effective_system_settings(self.db).site_trial_duration_hours

    def _site_trial_total_gb(self) -> int:
        return load_effective_system_settings(self.db).site_trial_total_gb

    def _site_trial_total_bytes(self) -> int:
        return self._site_trial_total_gb() * 1024 * 1024 * 1024

    def _get_or_create_user(
        self,
        telegram_user_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
    ) -> TelegramUser:
        user = self.users.get_by_telegram_id(telegram_user_id)
        if user:
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            if language_code is not None:
                user.language_code = language_code
            self.db.flush()
            return user

        user = TelegramUser(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            status=UserStatus.NEW.value,
        )
        self.users.create(user)
        self.audit.log(
            actor_type="bot",
            actor_id=str(telegram_user_id),
            event_type="telegram_user_created",
            entity_type="telegram_user",
            entity_id=str(telegram_user_id),
            message=f"Создан Telegram-пользователь {telegram_user_id}",
        )
        self.db.flush()
        return user

    def register_bot_user(self, user_id: int, bot_id: str) -> None:
        from sqlalchemy import text
        self.db.execute(
            text("""
                CREATE TABLE IF NOT EXISTS bot_users (
                    telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id),
                    managed_bot_id TEXT NOT NULL REFERENCES managed_bots(id),
                    PRIMARY KEY (telegram_user_id, managed_bot_id)
                )
            """)
        )
        self.db.execute(
            text("INSERT OR IGNORE INTO bot_users (telegram_user_id, managed_bot_id) VALUES (:u, :b)"),
            {"u": user_id, "b": bot_id}
        )
        self.db.flush()

    def _ensure_wallet(self, user: TelegramUser, managed_bot: ManagedBot):
        wallet = self.wallets.get_for_user_and_bot(user.id, managed_bot.id)
        if wallet:
            if wallet.trial_used_at is None:
                latest_trial = self.accesses.get_latest_trial_for_telegram_user_and_bot(user.telegram_user_id, managed_bot.id)
                if latest_trial:
                    wallet.trial_used_at = latest_trial.activated_at
                    wallet.trial_started_at = latest_trial.activated_at
                    wallet.trial_ends_at = latest_trial.expiry_at
                    self.db.flush()
            return wallet

        from app.models.user_wallet import UserWallet

        latest_trial = self.accesses.get_latest_trial_for_telegram_user_and_bot(user.telegram_user_id, managed_bot.id)
        wallet = UserWallet(
            telegram_user_id=user.id,
            managed_bot_id=managed_bot.id,
            balance_kopecks=0,
            trial_used_at=latest_trial.activated_at if latest_trial else None,
            trial_started_at=latest_trial.activated_at if latest_trial else None,
            trial_ends_at=latest_trial.expiry_at if latest_trial else None,
        )
        self.wallets.create(wallet)
        return wallet

    def _choose_server(self, product_code: str, *, trial_only: bool) -> Server:
        candidates = self.servers.get_active_candidates(product_code, trial_only=trial_only)
        if not candidates:
            if trial_only:
                raise ServiceError("Нет доступных серверов для выдачи теста", 409)
            raise ServiceError("Нет доступных серверов для выдачи платного доступа", 409)
        if len(candidates) == 1:
            return candidates[0]

        active_counts = self.accesses.get_active_counts_by_server(
            product_code=product_code,
            server_ids=[server.id for server in candidates],
            access_type="test" if trial_only else None,
        )

        def normalized_load(server: Server) -> float:
            weight = max(server.weight, 1)
            return active_counts.get(server.id, 0) / weight

        loads = {server.id: normalized_load(server) for server in candidates}
        min_load = min(loads.values())
        least_loaded = [server for server in candidates if loads[server.id] == min_load]
        weights = [max(server.weight, 1) for server in least_loaded]
        return choices(least_loaded, weights=weights, k=1)[0]

    def _choose_trial_server(self, product_code: str) -> Server:
        return self._choose_server(product_code, trial_only=True)

    def _choose_paid_server(self, product_code: str) -> Server:
        return self._choose_server(product_code, trial_only=False)

    def _resolve_managed_bot(self, bot_code: str) -> ManagedBot:
        managed_bot = self.managed_bots.get_by_code(bot_code)
        if not managed_bot or not managed_bot.is_active:
            raise ServiceError("Активный бот не найден", 404)
        return managed_bot

    def _resolve_site(self, site_code: str) -> Site:
        site = self.sites.get_by_code(site_code)
        if not site:
            raise ServiceError("Сайт не найден", 404)
        if site.deployment_status != "deployed":
            raise ServiceError("Сайт еще не развернут или находится в ошибке", 409)
        return site

    def _build_remote_client_payload(
        self,
        *,
        server: Server,
        email: str,
        client_uuid: str,
        expiry_at: datetime,
        device_limit: int,
        telegram_user_id: int | None,
        flow: str | None,
        total_bytes: int = 0,
    ) -> dict:
        payload = {
            "id": client_uuid,
            "email": email,
            "enable": True,
            "expiryTime": datetime_to_millis(expiry_at),
            "limitIp": device_limit,
            "totalGB": total_bytes,
            "reset": 0,
            "tgId": str(telegram_user_id) if telegram_user_id else "",
            "subId": secrets.token_hex(8),
        }
        selected_flow = flow or server.client_flow
        if selected_flow:
            payload["flow"] = selected_flow
        return payload

    def _build_remote_client_email(
        self,
        *,
        server: Server,
        product_code: str,
        email_root: str,
        client_uuid: str,
    ) -> str:
        alias = build_connection_alias(server.code, product_code)
        normalized_root = slugify_identifier(email_root, default="client", limit=40)
        suffix = client_uuid.split("-")[0]
        return f"{alias}-{normalized_root}-{suffix}"[:255]

    def _create_access_record(
        self,
        *,
        user: TelegramUser | None,
        managed_bot: ManagedBot | None,
        site: Site | None,
        server: Server,
        access_type: str,
        product_code: str,
        device_limit: int,
        expiry_at: datetime,
        remote_client: dict,
        config_bundle: dict,
        inbound_snapshot: dict,
        site_visitor_token: str | None = None,
        extra_metadata: dict | None = None,
    ) -> VpnAccess:
        access = VpnAccess(
            telegram_user_id=user.id if user else None,
            managed_bot_id=managed_bot.id if managed_bot else None,
            site_id=site.id if site else None,
            server_id=server.id,
            product_code=product_code,
            access_type=access_type,
            protocol="vless",
            status=AccessStatus.ACTIVE.value,
            inbound_id=server.inbound_id,
            client_uuid=remote_client["id"],
            client_email=remote_client["email"],
            remote_client_id=remote_client["id"],
            client_sub_id=remote_client.get("subId"),
            site_visitor_token=site_visitor_token,
            device_limit=device_limit,
            expiry_at=expiry_at,
            activated_at=datetime.now(timezone.utc),
            config_uri=config_bundle["uri"],
            config_text=config_bundle["text"],
            config_metadata={
                "remote_client": remote_client,
                "inbound_snapshot": inbound_snapshot,
                "query": config_bundle.get("query", {}),
                **(extra_metadata or {}),
            },
        )
        self.accesses.create(access)
        return access

    def _load_access_metadata(self, access: VpnAccess) -> tuple[dict, dict]:
        metadata = dict(access.config_metadata or {})
        remote_client = parse_json_field(metadata.get("remote_client"))
        inbound_snapshot = parse_json_field(metadata.get("inbound_snapshot"))
        if not remote_client:
            raise ServiceError("Не удалось восстановить metadata клиента для доступа", 500)
        if not inbound_snapshot:
            inbound_snapshot = build_three_x_ui_adapter(access.server).get_inbound(access.inbound_id)
            metadata["inbound_snapshot"] = inbound_snapshot
        return metadata, remote_client

    def _upsert_remote_client(self, access: VpnAccess, remote_client: dict) -> None:
        adapter = build_three_x_ui_adapter(access.server)
        try:
            adapter.update_client(access.remote_client_id, access.inbound_id, remote_client)
            return
        except ThreeXUIError as update_exc:
            try:
                adapter.add_client(access.inbound_id, remote_client)
                return
            except ThreeXUIError as add_exc:
                raise ServiceError(
                    f"Не удалось синхронизировать клиента в 3x-ui: update={update_exc}; add={add_exc}",
                    502,
                ) from add_exc

    def _activate_or_extend_existing_access(
        self,
        access: VpnAccess,
        *,
        expiry_at: datetime,
        access_type: str | None = None,
    ) -> VpnAccess:
        metadata, remote_client = self._load_access_metadata(access)
        remote_client["expiryTime"] = datetime_to_millis(expiry_at)
        remote_client["enable"] = True
        self._upsert_remote_client(access, remote_client)

        access.expiry_at = expiry_at
        access.status = AccessStatus.ACTIVE.value
        access.deactivated_at = None
        if access_type:
            access.access_type = access_type

        metadata["remote_client"] = remote_client
        access.config_metadata = metadata
        self._regenerate_access_config(access)
        return access

    def _create_user_access(
        self,
        *,
        user: TelegramUser,
        managed_bot: ManagedBot,
        access_type: str,
        duration_hours: int,
        server: Server | None = None,
    ) -> VpnAccess:
        product_code = managed_bot.product_code
        selected_server = server or (
            self._choose_trial_server(product_code) if access_type == AccessType.TEST.value else self._choose_paid_server(product_code)
        )
        adapter = build_three_x_ui_adapter(selected_server)
        expiry_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
        client_uuid = str(uuid4())
        email = self._build_remote_client_email(
            server=selected_server,
            product_code=product_code,
            email_root=str(user.telegram_user_id),
            client_uuid=client_uuid,
        )
        remote_client = self._build_remote_client_payload(
            server=selected_server,
            email=email,
            client_uuid=client_uuid,
            expiry_at=expiry_at,
            device_limit=1,
            telegram_user_id=user.telegram_user_id,
            flow=selected_server.client_flow,
        )
        try:
            inbound = adapter.get_inbound(selected_server.inbound_id)
            adapter.add_client(selected_server.inbound_id, remote_client)
        except ThreeXUIError as exc:
            raise ServiceError(f"Не удалось создать клиента в 3x-ui: {exc}", 502) from exc

        access_stub = VpnAccess(client_uuid=client_uuid, client_email=email, expiry_at=expiry_at)
        config_bundle = self.generator.generate_vless(
            server=selected_server,
            access=access_stub,
            inbound=inbound,
            client_payload=remote_client,
        )
        return self._create_access_record(
            user=user,
            managed_bot=managed_bot,
            site=None,
            server=selected_server,
            access_type=access_type,
            product_code=product_code,
            device_limit=1,
            expiry_at=expiry_at,
            remote_client=remote_client,
            config_bundle=config_bundle,
            inbound_snapshot=inbound,
        )

    def ensure_paid_access_for_user(
        self,
        *,
        managed_bot: ManagedBot,
        user: TelegramUser,
        duration_hours: int,
    ) -> VpnAccess:
        existing_access = self.accesses.get_latest_for_telegram_user_and_bot(user.telegram_user_id, managed_bot.id)
        if existing_access:
            expiry_at = max(existing_access.expiry_at, datetime.now(timezone.utc)) + timedelta(hours=duration_hours)
            access = self._activate_or_extend_existing_access(
                existing_access,
                expiry_at=expiry_at,
                access_type=AccessType.PAID.value,
            )
        else:
            access = self._create_user_access(
                user=user,
                managed_bot=managed_bot,
                access_type=AccessType.PAID.value,
                duration_hours=duration_hours,
            )
        user.status = UserStatus.ACTIVE.value
        return access

    def _refresh_user_status(self, user: TelegramUser | None) -> None:
        if user is None:
            return
        active_access = self.accesses.get_latest_active_for_telegram_user(user.telegram_user_id)
        if active_access:
            user.status = UserStatus.ACTIVE.value
            return
        if user.trial_used:
            user.status = UserStatus.EXPIRED.value
            return
        user.status = UserStatus.NEW.value

    def _regenerate_access_config(self, access: VpnAccess) -> bool:
        metadata = dict(access.config_metadata or {})
        inbound_snapshot = parse_json_field(metadata.get("inbound_snapshot"))
        remote_client = parse_json_field(metadata.get("remote_client"))
        if not inbound_snapshot or not remote_client:
            return False

        config_bundle = self.generator.generate_vless(
            server=access.server,
            access=access,
            inbound=inbound_snapshot,
            client_payload=remote_client,
        )
        metadata["query"] = config_bundle.get("query", {})
        access.config_metadata = metadata
        access.config_uri = config_bundle["uri"]
        access.config_text = config_bundle["text"]
        return True

    def request_trial(
        self,
        *,
        bot_code: str,
        telegram_user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
    ) -> BotTrialResponse:
        managed_bot = self._resolve_managed_bot(bot_code)
        user = self._get_or_create_user(
            telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )
        wallet = self._ensure_wallet(user, managed_bot)
        trial_already_used = wallet.trial_used_at is not None or self.accesses.has_trial_for_user_and_bot(user.id, managed_bot.id)
        if trial_already_used:
            raise ServiceError(
                "Тестовый доступ уже был выдан ранее",
                409,
            )

        trial_started_at = datetime.now(timezone.utc)
        existing_access = self.accesses.get_latest_for_telegram_user_and_bot(telegram_user_id, managed_bot.id)
        try:
            if existing_access:
                expiry_at = max(existing_access.expiry_at, trial_started_at) + timedelta(hours=self._trial_duration_hours())
                next_access_type = existing_access.access_type if existing_access.access_type == AccessType.PAID.value else AccessType.TEST.value
                access = self._activate_or_extend_existing_access(
                    existing_access,
                    expiry_at=expiry_at,
                    access_type=next_access_type,
                )
            else:
                access = self._create_user_access(
                    user=user,
                    managed_bot=managed_bot,
                    access_type=AccessType.TEST.value,
                    duration_hours=self._trial_duration_hours(),
                )
                expiry_at = access.expiry_at
        except ServiceError as exc:
            self.audit.log(
                actor_type="bot",
                actor_id=str(telegram_user_id),
                event_type="trial_issue_failed",
                entity_type="telegram_user",
                entity_id=str(telegram_user_id),
                level="error",
                message="Ошибка при выдаче теста",
                payload={"error": exc.message, "bot_code": managed_bot.code},
            )
            self.db.commit()
            raise
        user.trial_used = True
        user.trial_started_at = trial_started_at
        user.trial_ends_at = expiry_at
        user.status = UserStatus.ACTIVE.value
        wallet.trial_used_at = trial_started_at
        wallet.trial_started_at = trial_started_at
        wallet.trial_ends_at = expiry_at
        self.audit.log(
            actor_type="bot",
            actor_id=str(telegram_user_id),
            event_type="trial_issued",
            entity_type="vpn_access",
            entity_id=access.id,
            message=f"Выдан тест пользователю {telegram_user_id}",
            payload={
                "server_id": access.server_id,
                "expires_at": expiry_at.isoformat(),
                "bot_code": managed_bot.code,
                "product_code": managed_bot.product_code,
                "reused_existing_access": existing_access is not None,
            },
        )
        self.db.commit()
        self.db.refresh(access)
        return BotTrialResponse(
            message="Тестовый доступ выдан",
            bot_code=managed_bot.code,
            access_id=access.id,
            config_uri=access.config_uri or "",
            config_text=access.config_text or "",
            expires_at=access.expiry_at,
            server_name=access.server.name,
        )

    def _to_site_runtime_response(self, *, site: Site, access: VpnAccess) -> SiteRuntimeConfigResponse:
        expiry_label = access.expiry_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        return SiteRuntimeConfigResponse(
            message="Конфиг сайта готов",
            site_code=site.code,
            site_name=site.name,
            access_id=access.id,
            config_uri=access.config_uri or "",
            config_text=access.config_text or "",
            expires_at=access.expiry_at,
            expires_at_label=expiry_label,
            server_name=access.server.name,
            product_code=access.product_code,
        )

    def request_site_trial(
        self,
        *,
        site_code: str,
        visitor_token: str,
        client_ip: str | None,
        user_agent: str | None,
    ) -> SiteRuntimeConfigResponse:
        normalized_token = visitor_token.strip()
        if len(normalized_token) < 8:
            raise ServiceError("Некорректный visitor token", 400)

        site = self._resolve_site(site_code)
        active_access = self.accesses.get_latest_active_for_site_visitor(site.id, normalized_token)
        if active_access:
            if self._regenerate_access_config(active_access):
                self.db.commit()
                self.db.refresh(active_access)
            return self._to_site_runtime_response(site=site, access=active_access)

        if self.accesses.has_trial_for_site_visitor(site.id, normalized_token):
            raise ServiceError("Для этого посетителя тестовый доступ уже был выдан ранее", 409)

        product_code = "site"
        server = self._choose_trial_server(product_code)
        adapter = build_three_x_ui_adapter(server)
        expiry_at = datetime.now(timezone.utc) + timedelta(hours=self._site_trial_duration_hours())
        site_trial_total_gb = self._site_trial_total_gb()
        site_trial_total_bytes = self._site_trial_total_bytes()
        client_uuid = str(uuid4())
        email = self._build_remote_client_email(
            server=server,
            product_code=product_code,
            email_root=f"{site.code}-{normalized_token[:12]}",
            client_uuid=client_uuid,
        )
        remote_client = self._build_remote_client_payload(
            server=server,
            email=email,
            client_uuid=client_uuid,
            expiry_at=expiry_at,
            device_limit=1,
            telegram_user_id=None,
            flow=server.client_flow,
            total_bytes=site_trial_total_bytes,
        )
        try:
            inbound = adapter.get_inbound(server.inbound_id)
            adapter.add_client(server.inbound_id, remote_client)
        except ThreeXUIError as exc:
            self.audit.log(
                actor_type="system",
                event_type="site_trial_issue_failed",
                entity_type="site",
                entity_id=site.id,
                level="error",
                message=f"Ошибка выдачи сайта {site.name}",
                payload={"error": str(exc), "server_id": server.id, "site_code": site.code},
            )
            self.db.commit()
            raise ServiceError(f"Не удалось создать клиента в 3x-ui: {exc}", 502) from exc

        access_stub = VpnAccess(
            product_code=product_code,
            client_uuid=client_uuid,
            client_email=email,
            expiry_at=expiry_at,
        )
        config_bundle = self.generator.generate_vless(
            server=server,
            access=access_stub,
            inbound=inbound,
            client_payload=remote_client,
        )
        access = self._create_access_record(
            user=None,
            managed_bot=None,
            site=site,
            server=server,
            access_type=AccessType.TEST.value,
            product_code=product_code,
            device_limit=1,
            expiry_at=expiry_at,
            remote_client=remote_client,
            config_bundle=config_bundle,
            inbound_snapshot=inbound,
            site_visitor_token=normalized_token,
            extra_metadata={
                "issued_via": "site",
                "site_id": site.id,
                "site_code": site.code,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "traffic_limit_gb": site_trial_total_gb,
            },
        )
        self.audit.log(
            actor_type="system",
            event_type="site_trial_issued",
            entity_type="vpn_access",
            entity_id=access.id,
            message=f"Выдан site-доступ для сайта {site.name}",
            payload={
                "site_id": site.id,
                "site_code": site.code,
                "server_id": server.id,
                "visitor_token": normalized_token[:12],
                "product_code": product_code,
                "traffic_limit_gb": site_trial_total_gb,
            },
        )
        self.db.commit()
        self.db.refresh(access)
        return self._to_site_runtime_response(site=site, access=access)

    def create_manual_access(self, payload: AccessCreateRequest, actor_id: str | None = None) -> AccessRead:
        server = self.servers.get(payload.server_id)
        if not server:
            raise ServiceError("Сервер не найден", 404)

        managed_bot = None
        product_code = payload.product_code
        if payload.managed_bot_id:
            managed_bot = self.managed_bots.get(payload.managed_bot_id)
            if not managed_bot or not managed_bot.is_active:
                raise ServiceError("Бот не найден или отключен", 404)
            product_code = managed_bot.product_code
        elif payload.telegram_user_id is not None:
            raise ServiceError("Для Telegram-доступа нужно выбрать бота", 422)

        user = None
        if payload.telegram_user_id is not None:
            user = self._get_or_create_user(
                payload.telegram_user_id,
                username=payload.username,
                first_name=payload.first_name,
                last_name=payload.last_name,
                language_code=payload.language_code,
            )

        expiry_at = datetime.now(timezone.utc) + timedelta(hours=payload.duration_hours)
        client_uuid = str(uuid4())
        email_root = payload.telegram_user_id if payload.telegram_user_id is not None else "manual"
        email = self._build_remote_client_email(
            server=server,
            product_code=product_code,
            email_root=str(email_root),
            client_uuid=client_uuid,
        )
        remote_client = self._build_remote_client_payload(
            server=server,
            email=email,
            client_uuid=client_uuid,
            expiry_at=expiry_at,
            device_limit=payload.device_limit,
            telegram_user_id=payload.telegram_user_id,
            flow=payload.client_flow,
        )
        adapter = build_three_x_ui_adapter(server)
        try:
            inbound = adapter.get_inbound(server.inbound_id)
            adapter.add_client(server.inbound_id, remote_client)
        except ThreeXUIError as exc:
            raise ServiceError(f"Не удалось создать клиента на сервере: {exc}", 502) from exc

        access_stub = VpnAccess(client_uuid=client_uuid, client_email=email, expiry_at=expiry_at)
        config_bundle = self.generator.generate_vless(
            server=server, access=access_stub, inbound=inbound, client_payload=remote_client
        )
        access = self._create_access_record(
            user=user,
            managed_bot=managed_bot,
            site=None,
            server=server,
            access_type=payload.access_type,
            product_code=product_code,
            device_limit=payload.device_limit,
            expiry_at=expiry_at,
            remote_client=remote_client,
            config_bundle=config_bundle,
            inbound_snapshot=inbound,
        )
        if user:
            user.status = UserStatus.ACTIVE.value
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="access_created",
            entity_type="vpn_access",
            entity_id=access.id,
            message=f"Создан доступ {access.id}",
            payload={
                "server_id": server.id,
                "access_type": payload.access_type,
                "managed_bot_id": managed_bot.id if managed_bot else None,
            },
        )
        self.db.commit()
        self.db.refresh(access)
        return AccessRead.model_validate(access)

    def list_accesses(
        self,
        *,
        server_id: str | None = None,
        status: str | None = None,
        access_type: str | None = None,
        telegram_user_id: int | None = None,
    ) -> list[AccessRead]:
        accesses = self.accesses.list(
            server_id=server_id,
            status=status,
            access_type=access_type,
            telegram_user_id=telegram_user_id,
        )
        return [AccessRead.model_validate(item) for item in accesses]

    def extend_access(self, access_id: str, hours: int, actor_id: str | None = None) -> AccessRead:
        access = self.accesses.get(access_id)
        if not access:
            raise ServiceError("Доступ не найден", 404)
        expiry_at = max(access.expiry_at, datetime.now(timezone.utc)) + timedelta(hours=hours)
        self._activate_or_extend_existing_access(access, expiry_at=expiry_at)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="access_extended",
            entity_type="vpn_access",
            entity_id=access.id,
            message=f"Продлен доступ {access.id}",
            payload={"hours": hours, "expires_at": access.expiry_at.isoformat()},
        )
        self.db.commit()
        self.db.refresh(access)
        return AccessRead.model_validate(access)

    def _revoke_remote_access(self, access: VpnAccess) -> None:
        adapter = build_three_x_ui_adapter(access.server)
        adapter.delete_client(access.inbound_id, access.remote_client_id)

    def disable_access(self, access_id: str, actor_id: str | None = None) -> AccessRead:
        access = self.accesses.get(access_id)
        if not access:
            raise ServiceError("Доступ не найден", 404)
        if access.status in {AccessStatus.DISABLED.value, AccessStatus.DELETED.value}:
            return AccessRead.model_validate(access)
        try:
            self._revoke_remote_access(access)
        except ThreeXUIError as exc:
            raise ServiceError(f"Не удалось отключить клиента в 3x-ui: {exc}", 502) from exc
        access.status = AccessStatus.DISABLED.value
        access.deactivated_at = datetime.now(timezone.utc)
        self._refresh_user_status(access.telegram_user)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="access_disabled",
            entity_type="vpn_access",
            entity_id=access.id,
            message=f"Отключен доступ {access.id}",
        )
        self.db.commit()
        self.db.refresh(access)
        return AccessRead.model_validate(access)

    def delete_access(self, access_id: str, actor_id: str | None = None) -> None:
        access = self.accesses.get(access_id)
        if not access:
            raise ServiceError("Доступ не найден", 404)
        if access.status not in {AccessStatus.DELETED.value, AccessStatus.DISABLED.value}:
            try:
                self._revoke_remote_access(access)
            except ThreeXUIError:
                pass
        access.status = AccessStatus.DELETED.value
        access.deactivated_at = datetime.now(timezone.utc)
        self._refresh_user_status(access.telegram_user)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="access_deleted",
            entity_type="vpn_access",
            entity_id=access.id,
            message=f"Удален доступ {access.id}",
        )
        self.db.commit()

    def get_access_config(self, access_id: str) -> AccessConfigRead:
        access = self.accesses.get(access_id)
        if not access:
            raise ServiceError("Доступ не найден", 404)
        if self._regenerate_access_config(access):
            self.db.commit()
            self.db.refresh(access)
        if not access.config_uri or not access.config_text:
            raise ServiceError("Конфиг для доступа отсутствует", 404)
        return AccessConfigRead(
            access_id=access.id,
            config_uri=access.config_uri,
            config_text=access.config_text,
            expires_at=access.expiry_at,
        )

    def get_user_status(self, telegram_user_id: int, *, bot_code: str) -> BotUserRead:
        managed_bot = self._resolve_managed_bot(bot_code)
        user = self.users.get_by_telegram_id(telegram_user_id)
        if not user:
            raise ServiceError("Пользователь не найден", 404)
        wallet = self._ensure_wallet(user, managed_bot)
        latest_access = self.accesses.get_latest_for_telegram_user_and_bot(telegram_user_id, managed_bot.id)
        active_access = self.accesses.get_latest_active_for_telegram_user_and_bot(telegram_user_id, managed_bot.id)
        scoped_status = active_access.status if active_access else (latest_access.status if latest_access else UserStatus.NEW.value)
        return BotUserRead(
            bot_code=managed_bot.code,
            telegram_user_id=user.telegram_user_id,
            username=user.username,
            status=scoped_status,
            can_use_trial=wallet.trial_used_at is None,
            trial_used=wallet.trial_used_at is not None,
            trial_started_at=wallet.trial_started_at,
            trial_ends_at=wallet.trial_ends_at,
            balance_kopecks=wallet.balance_kopecks,
            balance_rub=f"{wallet.balance_kopecks // 100}.{wallet.balance_kopecks % 100:02d}",
            active_access_id=active_access.id if active_access else None,
            active_access_status=active_access.status if active_access else None,
            active_access_expires_at=active_access.expiry_at if active_access else None,
            server_name=active_access.server.name if active_access else None,
        )

    def get_latest_config_for_user(self, telegram_user_id: int, *, bot_code: str) -> AccessConfigRead:
        managed_bot = self._resolve_managed_bot(bot_code)
        access = self.accesses.get_latest_active_for_telegram_user_and_bot(telegram_user_id, managed_bot.id)
        if not access:
            raise ServiceError("Активный конфиг не найден", 404)
        return self.get_access_config(access.id)

    def expire_due_accesses(self) -> int:
        now = datetime.now(timezone.utc)
        expired = self.accesses.list_expired_active(now)
        processed = 0
        touched = False
        for access in expired:
            try:
                self._revoke_remote_access(access)
            except ThreeXUIError as exc:
                touched = True
                self.audit.log(
                    actor_type="system",
                    event_type="access_expire_revoke_failed",
                    entity_type="vpn_access",
                    entity_id=access.id,
                    level="error",
                    message=f"Ошибка деактивации просроченного доступа {access.id}",
                    payload={"error": str(exc)},
                )
                continue
            access.status = AccessStatus.EXPIRED.value
            access.deactivated_at = now
            self._refresh_user_status(access.telegram_user)
            
            # Отправка уведомления пользователю
            if access.telegram_user and access.managed_bot:
                text = (
                    f"⚠️ *Доступ истек*\n\n"
                    f"Ваша подписка на сервере *{access.server.name}* завершена.\n"
                    "Для продления, пожалуйста, воспользуйтесь меню бота."
                )
                self.bot_messenger.send_message_sync(access.managed_bot.code, access.telegram_user.telegram_user_id, text)

            self.audit.log(
                actor_type="system",
                event_type="access_expired",
                entity_type="vpn_access",
                entity_id=access.id,
                message=f"Истек доступ {access.id}",
                payload={"server_id": access.server_id},
            )
            processed += 1
            touched = True
        if touched:
            self.db.commit()
        return processed

    def notify_approaching_expiration(self) -> int:
        now = datetime.now(timezone.utc)
        items = self.accesses.list_approaching_expiration(now, window_hours=24)
        processed = 0
        for access in items:
            metadata = dict(access.config_metadata or {})
            if metadata.get("expiration_notified"):
                continue
            
            text = (
                f"⏳ *Ваш доступ скоро истечет*\n\n"
                f"Подписка на сервере *{access.server.name}* истекает "
                f"*{access.expiry_at.strftime('%d.%m.%Y %H:%M')} UTC*.\n"
                "Рекомендуем продлить заранее, чтобы не потерять связь!"
            )
            success = self.bot_messenger.send_message_sync(
                access.managed_bot.code, 
                access.telegram_user.telegram_user_id, 
                text
            )
            if success:
                metadata["expiration_notified"] = True
                access.config_metadata = metadata
                processed += 1
        
        if processed > 0:
            self.db.commit()
        return processed

    def send_mass_mailing(
        self,
        bot_code: str,
        text: str,
        image_url: str | None = None,
        image_bytes: bytes | None = None,
        image_filename: str | None = None,
    ) -> int:
        managed_bot = self._resolve_managed_bot(bot_code)
        from sqlalchemy import text as sql_text

        self.db.execute(
            sql_text("""
                CREATE TABLE IF NOT EXISTS bot_users (
                    telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id),
                    managed_bot_id TEXT NOT NULL REFERENCES managed_bots(id),
                    PRIMARY KEY (telegram_user_id, managed_bot_id)
                )
            """)
        )
        stmt = sql_text("""
            SELECT DISTINCT tu.telegram_user_id
            FROM telegram_users tu
            LEFT JOIN bot_users bu ON tu.id = bu.telegram_user_id
            LEFT JOIN vpn_accesses va ON tu.id = va.telegram_user_id
            WHERE bu.managed_bot_id = :bot_id OR va.managed_bot_id = :bot_id
        """)
        
        results = self.db.execute(stmt, {"bot_id": managed_bot.id}).all()
        chat_ids = [row.telegram_user_id for row in results if row.telegram_user_id]
        return self.bot_messenger.send_bulk_message_sync(
            managed_bot.code,
            chat_ids,
            text,
            image_url=image_url,
            image_bytes=image_bytes,
            image_filename=image_filename,
            parse_mode="Markdown",
        )
