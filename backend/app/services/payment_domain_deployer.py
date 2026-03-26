from __future__ import annotations

import json
import shlex

from app.schemas.payment_domain import PaymentDomainDeploymentPlanRead
from app.schemas.site import SiteConnectionPayload
from app.services.exceptions import ServiceError
from app.services.site_deployer import SiteDeployer


class PaymentDomainDeployer(SiteDeployer):
    def _build_nginx_config(self, *, plan: PaymentDomainDeploymentPlanRead) -> str:
        upstream = f"{plan.backend_api_base_url.rstrip('/')}/freekassa/"
        return (
            "server {\n"
            "    listen 80;\n"
            f"    server_name {plan.domain};\n\n"
            "    location /api/v1/freekassa/ {\n"
            f"        proxy_pass {upstream};\n"
            "        proxy_http_version 1.1;\n"
            "        proxy_set_header Host $host;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto $scheme;\n"
            "        proxy_set_header X-Forwarded-Host $host;\n"
            "        proxy_set_header X-Forwarded-Port $server_port;\n"
            "        proxy_ssl_server_name on;\n"
            "        proxy_read_timeout 60s;\n"
            "    }\n\n"
            "    location = /healthz {\n"
            "        default_type text/plain;\n"
            "        return 200 'ok';\n"
            "    }\n\n"
            "    location / {\n"
            "        return 404;\n"
            "    }\n"
            "}\n"
        )

    def _build_deployment_metadata(self, *, plan: PaymentDomainDeploymentPlanRead) -> str:
        payload = {
            "code": plan.payment_domain_code,
            "domain": plan.domain,
            "public_url": plan.public_url,
            "backend_api_base_url": plan.backend_api_base_url,
            "nginx_config_path": plan.nginx_config_path,
            "ssl_mode": plan.ssl_mode,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    def deploy(
        self,
        *,
        connection: SiteConnectionPayload,
        plan: PaymentDomainDeploymentPlanRead,
    ) -> dict:
        warnings = list(plan.warnings)

        with self._connect(connection) as client:
            probe = self._collect_probe(client, connection)
            effective_connection = connection.model_copy(update={"access_mode": "root"}) if probe.is_root else connection
            self._ensure_base_packages(
                client,
                effective_connection,
                probe.package_manager,
                include_nginx=True,
                include_certbot=True,
            )

            temp_root = f"{probe.home_dir.rstrip('/')}/.xray-payment-domain-deploy/{plan.payment_domain_code}"
            nginx_temp = f"{temp_root}/{plan.service_name}.conf"
            metadata_temp = f"{temp_root}/deployment.json"
            readme_temp = f"{temp_root}/README.txt"

            self._run(client, f"mkdir -p {shlex.quote(temp_root)}", connection=effective_connection)
            self._upload_text(client, nginx_temp, self._build_nginx_config(plan=plan))
            self._upload_text(client, metadata_temp, self._build_deployment_metadata(plan=plan))
            self._upload_text(
                client,
                readme_temp,
                (
                    "Managed payment domain reverse proxy for FreeKassa.\n"
                    f"Domain: {plan.domain}\n"
                    f"Backend API: {plan.backend_api_base_url}\n"
                    f"Nginx config: {plan.nginx_config_path}\n"
                ),
            )

            try:
                self._run(
                    client,
                    (
                        f"mkdir -p {shlex.quote(plan.remote_root)} && "
                        f"install -m 0644 {shlex.quote(metadata_temp)} {shlex.quote(f'{plan.remote_root}/deployment.json')} && "
                        f"install -m 0644 {shlex.quote(readme_temp)} {shlex.quote(f'{plan.remote_root}/README.txt')}"
                    ),
                    connection=effective_connection,
                    use_sudo=True,
                )
                self._run(
                    client,
                    f"install -m 0644 {shlex.quote(nginx_temp)} {shlex.quote(plan.nginx_config_path)}",
                    connection=effective_connection,
                    use_sudo=True,
                )
                self._run(
                    client,
                    "systemctl enable --now nginx && nginx -t && systemctl reload nginx",
                    connection=effective_connection,
                    use_sudo=True,
                )
                certbot = self._run(
                    client,
                    (
                        "certbot --nginx --redirect --non-interactive --agree-tos "
                        "--register-unsafely-without-email "
                        f"-d {shlex.quote(plan.domain)}"
                    ),
                    connection=effective_connection,
                    use_sudo=True,
                    check=False,
                )
                if certbot.exit_status != 0:
                    detail = certbot.stderr or certbot.stdout or "certbot завершился ошибкой"
                    raise ServiceError(f"Не удалось выпустить Let's Encrypt для {plan.domain}: {detail}", 502)
            finally:
                self._run(
                    client,
                    f"rm -rf {shlex.quote(temp_root)}",
                    connection=effective_connection,
                    check=False,
                )

        return {
            "public_url": plan.public_url,
            "ssl_mode": plan.ssl_mode,
            "connection_snapshot": probe.model_dump(),
            "deployment_snapshot": {
                **plan.model_dump(),
                "public_url": plan.public_url,
                "ssl_mode": plan.ssl_mode,
                "warnings": warnings,
            },
        }

    def remove(
        self,
        *,
        connection: SiteConnectionPayload,
        plan: PaymentDomainDeploymentPlanRead,
    ) -> dict:
        warnings = [
            "Let's Encrypt сертификаты и записи certbot не удалялись автоматически. При необходимости очистите их вручную."
        ]

        with self._connect(connection) as client:
            probe = self._collect_probe(client, connection)
            effective_connection = connection.model_copy(update={"access_mode": "root"}) if probe.is_root else connection

            self._run(
                client,
                f"rm -f {shlex.quote(plan.nginx_config_path)}",
                connection=effective_connection,
                use_sudo=True,
                check=False,
            )
            self._run(
                client,
                f"rm -rf {shlex.quote(plan.remote_root)}",
                connection=effective_connection,
                use_sudo=True,
                check=False,
            )
            nginx_reload = self._run(
                client,
                "if command -v nginx >/dev/null 2>&1; then nginx -t && systemctl reload nginx; fi",
                connection=effective_connection,
                use_sudo=True,
                check=False,
            )
            if nginx_reload.exit_status != 0:
                detail = nginx_reload.stderr or nginx_reload.stdout or "nginx не подтвердил reload"
                warnings.append(f"Nginx не удалось перезагрузить после удаления платежного домена: {detail}")

        return {
            "deleted_from_server": True,
            "warnings": warnings,
            "connection_snapshot": probe.model_dump(),
        }
