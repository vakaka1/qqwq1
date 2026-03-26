from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models.payment_domain import PaymentDomain
from app.models.system_settings import SystemSettings
from app.repositories.payment_domain import PaymentDomainRepository
from app.repositories.system_settings import SystemSettingsRepository
from app.schemas.payment_domain import (
    PaymentDomainDeleteRead,
    PaymentDomainDeploymentPlanRead,
    PaymentDomainProvisionRequest,
    PaymentDomainRead,
)
from app.schemas.site import SiteConnectionPayload, SiteConnectionProbeResponse
from app.services.audit import AuditService
from app.services.exceptions import ServiceError
from app.services.payment_domain_deployer import PaymentDomainDeployer
from app.services.system_settings import load_effective_system_settings
from app.utils.naming import build_unique_slug, slugify_identifier


class PaymentDomainService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.repo = PaymentDomainRepository(db)
        self.system_settings = SystemSettingsRepository(db)
        self.audit = AuditService(db)
        self.deployer = PaymentDomainDeployer()

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

    def _normalize_domain(self, value: str) -> str:
        raw = value.strip()
        if "://" in raw:
            parsed = urlsplit(raw)
            raw = parsed.hostname or parsed.netloc or parsed.path
        raw = raw.split("/")[0].split(":")[0].strip().lower().rstrip(".")
        if not raw:
            raise ServiceError("Укажите домен платежей", 400)
        return raw

    def _resolve_code(self, *, domain: str, current_payment_domain_id: str | None = None) -> str:
        base = slugify_identifier(domain, default="payment-domain", limit=48)
        existing_codes = {
            item.code
            for item in self.repo.list()
            if item.code and (current_payment_domain_id is None or item.id != current_payment_domain_id)
        }
        return build_unique_slug(base, existing_codes, limit=48)

    def _resolve_public_api_base_url(self, public_api_base_url: str | None = None) -> str:
        runtime_settings = load_effective_system_settings(self.db)
        api_prefix = self.settings.api_v1_prefix.rstrip("/")

        def with_api_prefix(candidate: str) -> str:
            normalized = candidate.strip().rstrip("/")
            if not normalized:
                return normalized
            parsed = urlsplit(normalized)
            path = parsed.path.rstrip("/")
            if path == api_prefix:
                return normalized
            rebuilt_path = f"{path}{api_prefix}" if path else api_prefix
            return urlunsplit(parsed._replace(path=rebuilt_path, query="", fragment=""))

        settings_url = with_api_prefix(runtime_settings.public_app_url)
        override_url = with_api_prefix(public_api_base_url or "")

        def is_local(candidate: str) -> bool:
            hostname = (urlsplit(candidate).hostname or "").lower()
            return hostname in {"", "localhost", "127.0.0.1", "0.0.0.0"}

        resolved = settings_url
        if override_url and is_local(settings_url):
            resolved = override_url

        parsed = urlsplit(resolved)
        if not parsed.scheme or not parsed.netloc:
            raise ServiceError("PUBLIC_APP_URL должен быть полным URL админки, доступным для внешнего proxy", 400)
        return resolved

    def _build_plan(
        self,
        payload: PaymentDomainProvisionRequest,
        *,
        public_api_base_url: str | None = None,
        current_payment_domain: PaymentDomain | None = None,
    ) -> tuple[PaymentDomainDeploymentPlanRead, str, str]:
        host = self._normalize_host(payload.connection.host)
        domain = self._normalize_domain(payload.settings.domain)
        existing = self.repo.get_by_domain(domain)
        if existing and (current_payment_domain is None or existing.id != current_payment_domain.id):
            raise ServiceError("Платежный домен с таким именем уже существует", 409)

        code = current_payment_domain.code if current_payment_domain else self._resolve_code(
            domain=domain,
            current_payment_domain_id=current_payment_domain.id if current_payment_domain else None,
        )
        backend_api_base_url = self._resolve_public_api_base_url(public_api_base_url)
        public_url = f"https://{domain}"
        service_name = f"xray-pay-{code}"

        plan = PaymentDomainDeploymentPlanRead(
            payment_domain_code=code,
            service_name=service_name,
            domain=domain,
            public_url=public_url,
            ssl_mode="letsencrypt",
            remote_root=f"/opt/xray-payment-domains/{code}",
            nginx_config_path=f"/etc/nginx/conf.d/{service_name}.conf",
            backend_api_base_url=backend_api_base_url,
            deploy_steps=[
                "Установить nginx, certbot и системные пакеты на целевой сервер.",
                "Создать выделенный remote root с метаданными платежного домена.",
                "Настроить nginx так, чтобы наружу публиковались только /api/v1/freekassa/* маршруты.",
                "Выпустить Let's Encrypt сертификат через certbot --nginx.",
                "Синхронизировать freekassa_public_url с новым платежным доменом.",
            ],
            warnings=[
                "Let's Encrypt сработает только если домен уже указывает на этот сервер.",
                "Домен будет proxy только для платежных маршрутов FreeKassa и не раскроет домен админки пользователю.",
            ],
        )
        return plan, host, domain

    def _to_read(self, payment_domain: PaymentDomain) -> PaymentDomainRead:
        return PaymentDomainRead.model_validate(
            {
                **payment_domain.__dict__,
                "has_password": bool(payment_domain.server_password_encrypted),
            }
        )

    def _connection_payload_from_payment_domain(self, payment_domain: PaymentDomain) -> SiteConnectionPayload:
        password = decrypt_secret(payment_domain.server_password_encrypted)
        if not password:
            raise ServiceError("Не удалось расшифровать пароль платежного домена", 500)
        return SiteConnectionPayload(
            access_mode=payment_domain.server_access_mode,
            host=payment_domain.server_host,
            port=payment_domain.server_port,
            username=payment_domain.server_username,
            password=password,
        )

    def _payload_from_payment_domain(self, payment_domain: PaymentDomain) -> PaymentDomainProvisionRequest:
        return PaymentDomainProvisionRequest(
            connection=self._connection_payload_from_payment_domain(payment_domain),
            settings={"domain": payment_domain.domain},
        )

    def _sync_freekassa_public_url(self, public_url: str | None) -> None:
        record = self.system_settings.get()
        if record is None:
            record = SystemSettings(id=1)
            self.system_settings.save(record)
        record.freekassa_public_url = public_url
        self.system_settings.save(record)
        self.db.flush()

    def list_payment_domains(self) -> list[PaymentDomainRead]:
        return [self._to_read(item) for item in self.repo.list()]

    def get_or_404(self, payment_domain_id: str) -> PaymentDomain:
        payment_domain = self.repo.get(payment_domain_id)
        if not payment_domain:
            raise ServiceError("Платежный домен не найден", 404)
        return payment_domain

    def probe_connection(self, payload: SiteConnectionPayload) -> SiteConnectionProbeResponse:
        normalized = payload.model_copy(update={"host": self._normalize_host(payload.host)})
        return self.deployer.probe_connection(normalized)

    def build_plan(
        self,
        payload: PaymentDomainProvisionRequest,
        *,
        public_api_base_url: str | None = None,
    ) -> PaymentDomainDeploymentPlanRead:
        normalized_connection = payload.connection.model_copy(update={"host": self._normalize_host(payload.connection.host)})
        normalized_payload = payload.model_copy(update={"connection": normalized_connection})
        plan, _, _ = self._build_plan(normalized_payload, public_api_base_url=public_api_base_url)
        return plan

    def create_payment_domain(
        self,
        payload: PaymentDomainProvisionRequest,
        actor_id: str | None = None,
        *,
        public_api_base_url: str | None = None,
    ) -> PaymentDomainRead:
        normalized_connection = payload.connection.model_copy(update={"host": self._normalize_host(payload.connection.host)})
        payload = payload.model_copy(update={"connection": normalized_connection})
        plan, host, domain = self._build_plan(payload, public_api_base_url=public_api_base_url)
        probe = self.deployer.probe_connection(normalized_connection)

        payment_domain = PaymentDomain(
            code=plan.payment_domain_code,
            domain=domain,
            public_url=plan.public_url,
            server_access_mode=payload.connection.access_mode,
            server_host=host,
            server_port=payload.connection.port,
            server_username=payload.connection.username.strip(),
            server_password_encrypted=encrypt_secret(payload.connection.password) or "",
            deployment_status="draft",
            ssl_mode=plan.ssl_mode,
            connection_snapshot=probe.model_dump(),
            deployment_snapshot=plan.model_dump(),
        )
        self.repo.create(payment_domain)
        self.db.flush()

        try:
            deployment = self.deployer.deploy(connection=normalized_connection, plan=plan)
            payment_domain.deployment_status = "deployed"
            payment_domain.public_url = str(deployment["public_url"])
            payment_domain.ssl_mode = str(deployment["ssl_mode"])
            payment_domain.last_deployed_at = datetime.now(timezone.utc)
            payment_domain.last_error = None
            payment_domain.connection_snapshot = dict(deployment["connection_snapshot"])
            payment_domain.deployment_snapshot = dict(deployment["deployment_snapshot"])
            self._sync_freekassa_public_url(payment_domain.public_url)
            self.audit.log(
                actor_type="admin",
                actor_id=actor_id,
                event_type="payment_domain_created",
                entity_type="payment_domain",
                entity_id=payment_domain.id,
                message=f"Создан и развернут платежный домен {payment_domain.domain}",
                payload={"payment_domain_id": payment_domain.id, "public_url": payment_domain.public_url},
            )
            self.db.commit()
            self.db.refresh(payment_domain)
            return self._to_read(payment_domain)
        except ServiceError as exc:
            payment_domain.deployment_status = "error"
            payment_domain.last_error = exc.message
            payment_domain.connection_snapshot = probe.model_dump()
            payment_domain.deployment_snapshot = {**plan.model_dump(), "warnings": plan.warnings}
            self.audit.log(
                actor_type="admin",
                actor_id=actor_id,
                event_type="payment_domain_deploy_failed",
                entity_type="payment_domain",
                entity_id=payment_domain.id,
                level="error",
                message=f"Ошибка развертывания платежного домена {payment_domain.domain}",
                payload={"payment_domain_id": payment_domain.id, "error": exc.message},
            )
            self.db.commit()
            raise

    def deploy_payment_domain(
        self,
        payment_domain_id: str,
        actor_id: str | None = None,
        *,
        public_api_base_url: str | None = None,
    ) -> PaymentDomainRead:
        payment_domain = self.get_or_404(payment_domain_id)
        payload = self._payload_from_payment_domain(payment_domain)
        plan, _, _ = self._build_plan(
            payload,
            public_api_base_url=public_api_base_url,
            current_payment_domain=payment_domain,
        )
        connection = payload.connection

        try:
            deployment = self.deployer.deploy(connection=connection, plan=plan)
            payment_domain.deployment_status = "deployed"
            payment_domain.public_url = str(deployment["public_url"])
            payment_domain.ssl_mode = str(deployment["ssl_mode"])
            payment_domain.last_deployed_at = datetime.now(timezone.utc)
            payment_domain.last_error = None
            payment_domain.connection_snapshot = dict(deployment["connection_snapshot"])
            payment_domain.deployment_snapshot = dict(deployment["deployment_snapshot"])
            self._sync_freekassa_public_url(payment_domain.public_url)
            self.audit.log(
                actor_type="admin",
                actor_id=actor_id,
                event_type="payment_domain_redeployed",
                entity_type="payment_domain",
                entity_id=payment_domain.id,
                message=f"Повторно развернут платежный домен {payment_domain.domain}",
                payload={"payment_domain_id": payment_domain.id, "public_url": payment_domain.public_url},
            )
            self.db.commit()
            self.db.refresh(payment_domain)
            return self._to_read(payment_domain)
        except ServiceError as exc:
            payment_domain.deployment_status = "error"
            payment_domain.last_error = exc.message
            self.audit.log(
                actor_type="admin",
                actor_id=actor_id,
                event_type="payment_domain_redeploy_failed",
                entity_type="payment_domain",
                entity_id=payment_domain.id,
                level="error",
                message=f"Ошибка повторного развертывания платежного домена {payment_domain.domain}",
                payload={"payment_domain_id": payment_domain.id, "error": exc.message},
            )
            self.db.commit()
            raise

    def delete_payment_domain(self, payment_domain_id: str, actor_id: str | None = None) -> PaymentDomainDeleteRead:
        payment_domain = self.get_or_404(payment_domain_id)
        warnings: list[str] = []
        deleted_from_server = False

        try:
            payload = self._payload_from_payment_domain(payment_domain)
            plan, _, _ = self._build_plan(payload, current_payment_domain=payment_domain)
            cleanup = self.deployer.remove(connection=payload.connection, plan=plan)
            warnings.extend(cleanup["warnings"])
            deleted_from_server = bool(cleanup["deleted_from_server"])
        except ServiceError as exc:
            warnings.append(
                f"Не удалось подключиться к серверу или завершить очистку: {exc.message}. Домен удален только из админки."
            )

        runtime_settings = load_effective_system_settings(self.db)
        current_public_url = (runtime_settings.freekassa_public_url or "").strip()
        if current_public_url and current_public_url == (payment_domain.public_url or "").strip():
            self._sync_freekassa_public_url(None)

        self.repo.delete(payment_domain)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="payment_domain_deleted",
            entity_type="payment_domain",
            entity_id=payment_domain_id,
            message=f"Удален платежный домен {payment_domain.domain}",
            payload={
                "payment_domain_id": payment_domain_id,
                "deleted_from_server": deleted_from_server,
                "warnings": warnings,
            },
        )
        self.db.commit()
        return PaymentDomainDeleteRead(
            payment_domain_id=payment_domain_id,
            domain=payment_domain.domain,
            deleted_from_admin=True,
            deleted_from_server=deleted_from_server,
            warnings=warnings,
        )
