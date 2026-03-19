from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models.managed_bot import ManagedBot
from app.models.site import Site
from app.models.vpn_access import VpnAccess
from app.repositories.managed_bot import ManagedBotRepository
from app.repositories.site import SiteRepository
from app.schemas.site import (
    SiteConnectionPayload,
    SiteConnectionProbeResponse,
    SiteDeleteRead,
    SiteDeploymentPlanRead,
    SiteManagedBotRead,
    SitePreviewRead,
    SiteProvisionRequest,
    SiteRead,
    SiteTemplateRead,
)
from app.services.audit import AuditService
from app.services.exceptions import ServiceError
from app.services.site_deployer import SiteDeployer
from app.services.site_templates import SiteTemplateDefinition, SiteTemplateService
from app.services.system_settings import load_effective_system_settings
from app.utils.naming import build_unique_slug, slugify_identifier


class SiteService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = SiteRepository(db)
        self.bots = ManagedBotRepository(db)
        self.audit = AuditService(db)
        self.templates = SiteTemplateService()
        self.deployer = SiteDeployer()

    def _normalize_host(self, value: str) -> str:
        raw = value.strip()
        if "://" in raw:
            parsed = urlsplit(raw)
            raw = parsed.hostname or parsed.netloc or parsed.path
        raw = raw.split("/")[0].strip()
        if raw.count(":") == 1 and not raw.startswith("["):
            raw = raw.rsplit(":", 1)[0]
        if not raw:
            raise ServiceError("Укажите IP или домен сервера", 400)
        return raw.lower()

    def _normalize_domain(self, value: str | None, *, publish_mode: str) -> str | None:
        if publish_mode != "domain":
            return None
        raw = (value or "").strip()
        if not raw:
            raise ServiceError("Укажите домен сайта", 400)
        if "://" in raw:
            parsed = urlsplit(raw)
            raw = parsed.hostname or parsed.netloc or parsed.path
        raw = raw.split("/")[0].split(":")[0].strip().lower().rstrip(".")
        if not raw:
            raise ServiceError("Укажите домен сайта", 400)
        return raw

    def _resolve_bot_or_404(self, managed_bot_id: str) -> ManagedBot:
        managed_bot = self.bots.get(managed_bot_id)
        if not managed_bot:
            raise ServiceError("Бот не найден", 404)
        if not managed_bot.is_active:
            raise ServiceError("Выбранный бот отключен", 400)
        if not (managed_bot.telegram_bot_username or "").strip():
            raise ServiceError("У выбранного бота не задан @username для публичного сайта", 400)
        return managed_bot

    def _resolve_site_code(
        self,
        *,
        preferred: str | None,
        name: str,
        host: str,
        current_site_id: str | None = None,
    ) -> str:
        base = slugify_identifier(preferred or name or host, default="site")
        existing_codes = {
            item.code
            for item in self.repo.list()
            if item.code and (current_site_id is None or item.id != current_site_id)
        }
        return build_unique_slug(base, existing_codes)

    def _resolve_public_api_base_url(self, public_api_base_url: str | None = None) -> str:
        runtime_settings = load_effective_system_settings(self.db)
        settings_url = f"{runtime_settings.public_app_url.rstrip('/')}{self.settings.api_v1_prefix}"
        override_url = (public_api_base_url or "").strip().rstrip("/")

        def is_local(candidate: str) -> bool:
            hostname = (urlsplit(candidate).hostname or "").lower()
            return hostname in {"", "localhost", "127.0.0.1", "0.0.0.0"}

        resolved = settings_url
        if override_url:
            resolved = settings_url if is_local(override_url) and not is_local(settings_url) else override_url

        parsed = urlsplit(resolved)
        if not parsed.scheme or not parsed.netloc:
            raise ServiceError("PUBLIC_APP_URL должен быть полным URL админки, доступным для внешних сайтов", 400)
        return resolved

    def _validate_site_runtime_settings(self) -> None:
        token = self.settings.site_runtime_token.strip()
        if not token or token == "change-me-site-runtime-token":
            raise ServiceError(
                "SITE_RUNTIME_TOKEN оставлен значением по умолчанию. Задайте секрет в .env перед развертыванием сайтов.",
                400,
            )

    def _normalize_cloudflare_public_url(self, public_url: str) -> str:
        normalized_url = public_url.strip()
        parsed = urlsplit(normalized_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not hostname.endswith(".trycloudflare.com"):
            raise ServiceError("Ожидался HTTPS-адрес Cloudflare Quick Tunnel", 400)
        return normalized_url

    def _store_cloudflare_public_url(self, site: Site, public_url: str) -> None:
        normalized_url = self._normalize_cloudflare_public_url(public_url)
        snapshot = dict(site.deployment_snapshot or {})
        snapshot["public_url"] = normalized_url
        snapshot["cloudflare_public_url"] = normalized_url
        site.public_url = normalized_url
        site.deployment_snapshot = snapshot

    def _ensure_proxy_port_available(
        self,
        *,
        host: str,
        proxy_port: int,
        current_site_id: str | None = None,
    ) -> None:
        for site in self.repo.list():
            if current_site_id is not None and site.id == current_site_id:
                continue
            if site.server_host == host and site.proxy_port == proxy_port:
                raise ServiceError(
                    f"На сервере {host} уже есть сайт {site.name} с внутренним портом {proxy_port}. Укажите другой порт.",
                    409,
                )

    def _build_plan(
        self,
        payload: SiteProvisionRequest,
        *,
        current_site: Site | None = None,
    ) -> tuple[SiteDeploymentPlanRead, ManagedBot, SiteTemplateDefinition, str, str | None]:
        host = self._normalize_host(payload.connection.host)
        publish_mode = payload.settings.publish_mode
        domain = self._normalize_domain(payload.settings.domain, publish_mode=publish_mode)
        managed_bot = self._resolve_bot_or_404(payload.settings.managed_bot_id)
        template = self.templates.get_definition_or_404(payload.template.key)
        site_code = current_site.code if current_site else self._resolve_site_code(
            preferred=domain if publish_mode == "domain" else payload.settings.name,
            name=payload.settings.name,
            host=host,
        )
        proxy_port = payload.settings.proxy_port
        self._ensure_proxy_port_available(
            host=host,
            proxy_port=proxy_port,
            current_site_id=current_site.id if current_site else None,
        )
        service_name = f"xray-site-{site_code}"
        server_name = domain or host
        warnings: list[str] = []
        public_url = f"https://{domain or host}"
        nginx_config_path = f"/etc/nginx/conf.d/{service_name}.conf"
        cloudflare_unit_path: str | None = None
        cloudflare_url_file: str | None = None
        cloudflare_log_file: str | None = None
        remote_root = f"/opt/xray-sites/{site_code}"

        if publish_mode == "domain":
            ssl_mode = "letsencrypt"
            warnings.append("Let's Encrypt сработает только если домен уже указывает на этот сервер.")
            deploy_steps = [
                "Установить Python, nginx и вспомогательные пакеты на целевой сервер.",
                f"Собрать Flask-службу {service_name} на 127.0.0.1:{proxy_port}.",
                f"Загрузить HTML-шаблон {template.filename} и подставить имя сайта и ссылки на Telegram.",
                "Настроить nginx как reverse proxy на 80/443.",
                "Подключить Let's Encrypt для домена.",
            ]
        elif publish_mode == "cloudflare_tunnel":
            ssl_mode = "cloudflare"
            public_url = "https://<будет-сгенерирован>.trycloudflare.com"
            nginx_config_path = None
            cloudflare_unit_path = f"/etc/systemd/system/{service_name}-cloudflared.service"
            cloudflare_url_file = f"{remote_root}/run/trycloudflare.url"
            cloudflare_log_file = f"{remote_root}/run/cloudflared.log"
            warnings.append(
                "Cloudflare Quick Tunnel выдает случайный адрес trycloudflare.com. После рестарта туннеля или сервера адрес может измениться."
            )
            warnings.append(
                "Quick Tunnel подходит как быстрый HTTPS-вариант без домена, но это не production-режим Cloudflare."
            )
            deploy_steps = [
                "Установить Python и cloudflared на целевой сервер.",
                f"Собрать Flask-службу {service_name} на 127.0.0.1:{proxy_port}.",
                f"Загрузить HTML-шаблон {template.filename} и подставить имя сайта и ссылки на Telegram.",
                "Создать systemd-службу cloudflared с автозапуском.",
                f"Поднять quick tunnel до 127.0.0.1:{proxy_port} и сохранить выданный trycloudflare URL.",
            ]
        else:
            ssl_mode = "self-signed"
            warnings.append(
                "Сайт будет доступен по IP с self-signed сертификатом. Браузер покажет предупреждение безопасности."
            )
            deploy_steps = [
                "Установить Python, nginx и вспомогательные пакеты на целевой сервер.",
                f"Собрать Flask-службу {service_name} на 127.0.0.1:{proxy_port}.",
                f"Загрузить HTML-шаблон {template.filename} и подставить имя сайта и ссылки на Telegram.",
                "Настроить nginx как reverse proxy на 80/443.",
                "Сгенерировать self-signed сертификат для HTTPS по IP.",
            ]

        plan = SiteDeploymentPlanRead(
            site_code=site_code,
            service_name=service_name,
            template_name=template.name,
            publish_mode=publish_mode,
            server_name=server_name,
            public_url=public_url,
            proxy_port=proxy_port,
            ssl_mode=ssl_mode,
            remote_root=remote_root,
            app_dir=f"{remote_root}/app",
            nginx_config_path=nginx_config_path,
            systemd_unit_path=f"/etc/systemd/system/{service_name}.service",
            cloudflare_unit_path=cloudflare_unit_path,
            cloudflare_url_file=cloudflare_url_file,
            cloudflare_log_file=cloudflare_log_file,
            deploy_steps=deploy_steps,
            warnings=warnings,
        )
        return plan, managed_bot, template, host, domain

    def _build_template_context(
        self,
        *,
        payload: SiteProvisionRequest,
        managed_bot: ManagedBot,
        public_url: str,
        domain: str | None,
    ) -> dict[str, str]:
        runtime_settings = load_effective_system_settings(self.db)
        bot_username = (managed_bot.telegram_bot_username or "").strip().lstrip("@")
        telegram_url = f"https://t.me/{bot_username}"
        telegram_start_url = f"{telegram_url}?start=site"
        return {
            "SERVICE_NAME": payload.settings.name.strip(),
            "SITE_NAME": payload.settings.name.strip(),
            "BOT_NAME": managed_bot.name,
            "BOT_USERNAME": f"@{bot_username}",
            "TELEGRAM_URL": telegram_url,
            "TELEGRAM_START_URL": telegram_start_url,
            "BOT_START_URL": "/config",
            "CONFIG_URL": "/config",
            "PUBLIC_URL": public_url,
            "DOMAIN": domain or "",
            "SITE_TRIAL_DURATION_HOURS": str(runtime_settings.site_trial_duration_hours),
            "SITE_TRIAL_TOTAL_GB": str(runtime_settings.site_trial_total_gb),
        }

    def _to_read(self, site: Site) -> SiteRead:
        template_map = {item.key: item for item in self.templates.list_definitions()}
        template_name = template_map.get(site.template_key).name if site.template_key in template_map else site.template_key
        managed_bot = site.managed_bot
        publish_mode = site.publish_mode or ("domain" if site.domain else "ip")
        return SiteRead.model_validate(
            {
                **site.__dict__,
                "publish_mode": publish_mode,
                "template_name": template_name,
                "has_password": bool(site.server_password_encrypted),
                "managed_bot": SiteManagedBotRead(
                    id=managed_bot.id,
                    code=managed_bot.code,
                    name=managed_bot.name,
                    telegram_bot_username=managed_bot.telegram_bot_username,
                ),
            }
        )

    def list_sites(self) -> list[SiteRead]:
        return [self._to_read(item) for item in self.repo.list()]

    def list_templates(self) -> list[SiteTemplateRead]:
        return self.templates.list_templates()

    def get_or_404(self, site_id: str) -> Site:
        site = self.repo.get(site_id)
        if not site:
            raise ServiceError("Сайт не найден", 404)
        return site

    def probe_connection(self, payload: SiteConnectionPayload) -> SiteConnectionProbeResponse:
        normalized = payload.model_copy(update={"host": self._normalize_host(payload.host)})
        return self.deployer.probe_connection(normalized)

    def render_preview(self, payload: SiteProvisionRequest) -> SitePreviewRead:
        plan, managed_bot, _, _, domain = self._build_plan(payload)
        context = self._build_template_context(
            payload=payload,
            managed_bot=managed_bot,
            public_url=plan.public_url,
            domain=domain,
        )
        rendered = self.templates.render(payload.template.key, context)
        return SitePreviewRead(
            html=rendered,
            telegram_url=context["TELEGRAM_URL"],
            warnings=plan.warnings,
        )

    def build_plan(self, payload: SiteProvisionRequest) -> SiteDeploymentPlanRead:
        plan, _, _, _, _ = self._build_plan(payload)
        return plan

    def _connection_payload_from_site(self, site: Site) -> SiteConnectionPayload:
        password = decrypt_secret(site.server_password_encrypted)
        if not password:
            raise ServiceError("Для сайта не найден сохраненный пароль подключения", 409)
        return SiteConnectionPayload(
            access_mode=site.server_access_mode,
            host=site.server_host,
            port=site.server_port,
            username=site.server_username,
            password=password,
        )

    def _payload_from_site(
        self,
        site: Site,
        *,
        connection: SiteConnectionPayload | None = None,
    ) -> SiteProvisionRequest:
        return SiteProvisionRequest(
            connection=connection or self._connection_payload_from_site(site),
            settings={
                "name": site.name,
                "managed_bot_id": site.managed_bot_id,
                "publish_mode": site.publish_mode or ("domain" if site.domain else "ip"),
                "domain": site.domain,
                "proxy_port": site.proxy_port,
            },
            template={"key": site.template_key},
        )

    def _deploy_existing_site(
        self,
        site: Site,
        *,
        public_api_base_url: str | None = None,
    ) -> tuple[SiteProvisionRequest, SiteDeploymentPlanRead, dict]:
        connection = self._connection_payload_from_site(site)
        payload = self._payload_from_site(site, connection=connection)
        runtime_base_url = self._resolve_public_api_base_url(public_api_base_url)
        self._validate_site_runtime_settings()
        plan, managed_bot, _, _, domain = self._build_plan(payload, current_site=site)
        context = self._build_template_context(
            payload=payload,
            managed_bot=managed_bot,
            public_url=plan.public_url,
            domain=domain,
        )
        rendered_html = self.templates.render(site.template_key, context)
        deployment = self.deployer.deploy(
            connection=connection,
            plan=plan,
            rendered_html=rendered_html,
            site_name=site.name,
            telegram_url=context["TELEGRAM_URL"],
            telegram_handle=context["BOT_USERNAME"],
            backend_base_url=runtime_base_url,
            site_runtime_token=self.settings.site_runtime_token,
        )
        return payload, plan, deployment

    def create_site(
        self,
        payload: SiteProvisionRequest,
        actor_id: str | None = None,
        *,
        public_api_base_url: str | None = None,
    ) -> SiteRead:
        normalized_connection = payload.connection.model_copy(
            update={"host": self._normalize_host(payload.connection.host)}
        )
        payload = payload.model_copy(update={"connection": normalized_connection})
        runtime_base_url = self._resolve_public_api_base_url(public_api_base_url)
        self._validate_site_runtime_settings()
        plan, managed_bot, _, host, domain = self._build_plan(payload)
        probe = self.deployer.probe_connection(normalized_connection)
        context = self._build_template_context(
            payload=payload,
            managed_bot=managed_bot,
            public_url=plan.public_url,
            domain=domain,
        )
        rendered_html = self.templates.render(payload.template.key, context)

        site = Site(
            code=plan.site_code,
            name=payload.settings.name.strip(),
            publish_mode=payload.settings.publish_mode,
            domain=domain or None,
            public_url=plan.public_url,
            template_key=payload.template.key,
            server_access_mode=payload.connection.access_mode,
            server_host=host,
            server_port=payload.connection.port,
            server_username=payload.connection.username.strip(),
            proxy_port=plan.proxy_port,
            server_password_encrypted=encrypt_secret(payload.connection.password) or "",
            managed_bot_id=managed_bot.id,
            deployment_status="draft",
            ssl_mode=plan.ssl_mode,
            connection_snapshot=probe.model_dump(),
            deployment_snapshot=plan.model_dump(),
        )
        self.repo.create(site)
        self.db.flush()

        try:
            deployment = self.deployer.deploy(
                connection=normalized_connection,
                plan=plan,
                rendered_html=rendered_html,
                site_name=site.name,
                telegram_url=context["TELEGRAM_URL"],
                telegram_handle=context["BOT_USERNAME"],
                backend_base_url=runtime_base_url,
                site_runtime_token=self.settings.site_runtime_token,
            )
            site.deployment_status = "deployed"
            site.public_url = str(deployment["public_url"])
            site.ssl_mode = str(deployment["ssl_mode"])
            site.last_deployed_at = datetime.now(timezone.utc)
            site.last_error = None
            site.connection_snapshot = dict(deployment["connection_snapshot"])
            site.deployment_snapshot = dict(deployment["deployment_snapshot"])
            self.audit.log(
                actor_type="admin",
                actor_id=actor_id,
                event_type="site_created",
                entity_type="site",
                entity_id=site.id,
                message=f"Создан и развернут сайт {site.name}",
                payload={"site_id": site.id, "public_url": site.public_url},
            )
            self.db.commit()
            self.db.refresh(site)
            return self._to_read(site)
        except ServiceError as exc:
            site.deployment_status = "error"
            site.last_error = exc.message
            site.connection_snapshot = probe.model_dump()
            site.deployment_snapshot = {**plan.model_dump(), "warnings": plan.warnings}
            self.audit.log(
                actor_type="admin",
                actor_id=actor_id,
                event_type="site_deploy_failed",
                entity_type="site",
                entity_id=site.id,
                level="error",
                message=f"Ошибка развертывания сайта {site.name}",
                payload={"site_id": site.id, "error": exc.message},
            )
            self.db.commit()
            raise

    def report_cloudflare_public_url(self, *, site_code: str, public_url: str) -> dict[str, str]:
        site = self.repo.get_by_code(site_code.strip())
        if not site:
            raise ServiceError("Сайт не найден", 404)
        if site.publish_mode != "cloudflare_tunnel":
            raise ServiceError("Cloudflare URL можно обновлять только для сайтов с tunnel-режимом", 409)
        self._store_cloudflare_public_url(site, public_url)
        self.db.commit()
        return {"status": "ok", "public_url": site.public_url or ""}

    def refresh_cloudflare_public_url(self, site_id: str, actor_id: str | None = None) -> SiteRead:
        site = self.get_or_404(site_id)
        if site.publish_mode != "cloudflare_tunnel":
            raise ServiceError("Обновление URL доступно только для сайтов с Cloudflare Tunnel", 409)

        connection = self._connection_payload_from_site(site)
        payload = self._payload_from_site(site, connection=connection)
        plan, _, _, _, _ = self._build_plan(payload, current_site=site)
        refreshed = self.deployer.read_cloudflare_public_url(connection=connection, plan=plan)

        self._store_cloudflare_public_url(site, str(refreshed["public_url"]))
        site.connection_snapshot = dict(refreshed["connection_snapshot"])
        site.last_error = None
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="site_cloudflare_url_refreshed",
            entity_type="site",
            entity_id=site.id,
            message=f"Обновлен Cloudflare URL сайта {site.name}",
            payload={"site_id": site.id, "public_url": site.public_url},
        )
        self.db.commit()
        self.db.refresh(site)
        return self._to_read(site)

    def delete_site(self, site_id: str, actor_id: str | None = None) -> SiteDeleteRead:
        site = self.get_or_404(site_id)
        warnings: list[str] = []
        deleted_from_server = False

        try:
            connection = self._connection_payload_from_site(site)
            payload = self._payload_from_site(site, connection=connection)
            plan, _, _, _, _ = self._build_plan(payload, current_site=site)
            cleanup = self.deployer.remove(connection=connection, plan=plan)
            warnings.extend(cleanup["warnings"])
            deleted_from_server = bool(cleanup["deleted_from_server"])
        except ServiceError as exc:
            warnings.append(
                f"Не удалось подключиться к серверу или завершить очистку: {exc.message}. Сайт удален только из админки."
            )

        self.db.execute(
            update(VpnAccess)
            .where(VpnAccess.site_id == site.id)
            .values(site_id=None)
        )
        self.repo.delete(site)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="site_deleted",
            entity_type="site",
            entity_id=site_id,
            message=f"Удален сайт {site.name}",
            payload={
                "site_id": site_id,
                "deleted_from_server": deleted_from_server,
                "warnings": warnings,
            },
        )
        self.db.commit()
        return SiteDeleteRead(
            site_id=site_id,
            site_name=site.name,
            deleted_from_admin=True,
            deleted_from_server=deleted_from_server,
            warnings=warnings,
        )

    def deploy_site(
        self,
        site_id: str,
        actor_id: str | None = None,
        *,
        public_api_base_url: str | None = None,
    ) -> SiteRead:
        site = self.get_or_404(site_id)
        try:
            _, _, deployment = self._deploy_existing_site(site, public_api_base_url=public_api_base_url)
            site.deployment_status = "deployed"
            site.public_url = str(deployment["public_url"])
            site.ssl_mode = str(deployment["ssl_mode"])
            site.last_deployed_at = datetime.now(timezone.utc)
            site.last_error = None
            site.connection_snapshot = dict(deployment["connection_snapshot"])
            site.deployment_snapshot = dict(deployment["deployment_snapshot"])
            self.audit.log(
                actor_type="admin",
                actor_id=actor_id,
                event_type="site_redeployed",
                entity_type="site",
                entity_id=site.id,
                message=f"Повторно развернут сайт {site.name}",
                payload={"site_id": site.id, "public_url": site.public_url},
            )
            self.db.commit()
            self.db.refresh(site)
            return self._to_read(site)
        except ServiceError as exc:
            site.deployment_status = "error"
            site.last_error = exc.message
            self.audit.log(
                actor_type="admin",
                actor_id=actor_id,
                event_type="site_redeploy_failed",
                entity_type="site",
                entity_id=site.id,
                level="error",
                message=f"Ошибка повторного развертывания сайта {site.name}",
                payload={"site_id": site.id, "error": exc.message},
            )
            self.db.commit()
            raise
