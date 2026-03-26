from __future__ import annotations

import json
import shlex
from html import escape

from app.schemas.payment_domain import PaymentDomainDeploymentPlanRead
from app.schemas.site import SiteConnectionPayload
from app.services.exceptions import ServiceError
from app.services.site_deployer import SiteDeployer


class PaymentDomainDeployer(SiteDeployer):
    def _static_root(self, *, plan: PaymentDomainDeploymentPlanRead) -> str:
        return f"{plan.remote_root}/www"

    def _build_nginx_config(self, *, plan: PaymentDomainDeploymentPlanRead) -> str:
        upstream = f"{plan.backend_api_base_url.rstrip('/')}/freekassa/"
        static_root = self._static_root(plan=plan)
        return f"""
server {{
    listen 80;
    server_name {plan.domain};
    charset utf-8;
    root {static_root};
    index index.html;
    error_page 404 /404.html;

    location /api/v1/freekassa/ {{
        proxy_pass {upstream};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_ssl_server_name on;
        proxy_read_timeout 60s;
    }}

    location = /healthz {{
        default_type text/plain;
        return 200 'ok';
    }}

    location = /favicon.ico {{
        return 204;
    }}

    location = /404.html {{
        internal;
    }}

    location = / {{
        try_files /index.html =404;
    }}

    location / {{
        try_files $uri $uri/ =404;
    }}
}}
""".strip() + "\n"

    def _render_static_page(
        self,
        *,
        title: str,
        eyebrow: str,
        message: str,
        detail: str,
        domain: str,
        status_label: str,
        action_label: str | None = None,
        action_href: str | None = None,
    ) -> str:
        safe_title = escape(title)
        safe_eyebrow = escape(eyebrow)
        safe_message = escape(message)
        safe_detail = escape(detail)
        safe_domain = escape(domain)
        safe_status = escape(status_label)
        action_markup = ""
        if action_label and action_href:
            action_markup = f'<a class="primary" href="{escape(action_href, quote=True)}">{escape(action_label)}</a>'
        return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
        background: radial-gradient(circle at top left, rgba(15,118,110,.14), transparent 34%), linear-gradient(180deg, #f5f8fc 0%, #dce8f7 100%);
        font-family: Manrope, system-ui, sans-serif;
        color: #0f172a;
      }}
      main {{
        width: min(720px, 100%);
        padding: 32px;
        border-radius: 30px;
        border: 1px solid rgba(148,163,184,.25);
        background: rgba(255,255,255,.94);
        box-shadow: 0 24px 70px rgba(15,23,42,.14);
      }}
      .eyebrow {{
        display: inline-block;
        padding: 10px 14px;
        border-radius: 999px;
        background: rgba(15,118,110,.1);
        color: #0f766e;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: .14em;
        text-transform: uppercase;
      }}
      h1 {{
        margin: 18px 0 12px;
        font-size: clamp(2.4rem, 6vw, 4rem);
        line-height: .94;
        letter-spacing: -.07em;
      }}
      p {{
        margin: 0;
        color: #526076;
        line-height: 1.7;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 14px;
        margin-top: 24px;
      }}
      .tile {{
        padding: 16px 18px;
        border-radius: 22px;
        background: #f8fafc;
        border: 1px solid rgba(203,213,225,.8);
      }}
      .tile span {{
        display: block;
        color: #64748b;
        font-size: .82rem;
        margin-bottom: 8px;
      }}
      .tile strong {{
        display: block;
        font-size: 1rem;
        line-height: 1.45;
        word-break: break-word;
      }}
      .note {{
        margin-top: 22px;
        padding: 18px 20px;
        border-radius: 24px;
        background: linear-gradient(135deg, rgba(15,118,110,.08), rgba(11,94,215,.08));
      }}
      .actions {{
        margin-top: 22px;
      }}
      .primary {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 52px;
        padding: 0 20px;
        border-radius: 16px;
        background: linear-gradient(135deg, #0f766e, #0b5ed7);
        color: #fff;
        text-decoration: none;
        font-weight: 700;
      }}
    </style>
  </head>
  <body>
    <main>
      <div class="eyebrow">{safe_eyebrow}</div>
      <h1>{safe_title}</h1>
      <p>{safe_message}</p>
      <div class="grid">
        <section class="tile"><span>Домен</span><strong>{safe_domain}</strong></section>
        <section class="tile"><span>Назначение</span><strong>Платежный шлюз и страницы оплаты</strong></section>
        <section class="tile"><span>Статус</span><strong>{safe_status}</strong></section>
      </div>
      <div class="note">{safe_detail}</div>
      <div class="actions">{action_markup}</div>
    </main>
  </body>
</html>"""

    def _build_index_page(self, *, plan: PaymentDomainDeploymentPlanRead) -> str:
        return self._render_static_page(
            title="Безопасная оплата",
            eyebrow="Payment domain",
            message="Это выделенный домен оплаты. Обычно сюда попадают по персональной ссылке из Telegram-бота перед оплатой по СБП.",
            detail="Если вы открыли адрес вручную, вернитесь в бота и перейдите по персональной ссылке оплаты. Корневой адрес домена служит только витриной и не открывает чужие счета.",
            domain=plan.domain,
            status_label="Готов к оплате",
        )

    def _build_not_found_page(self, *, plan: PaymentDomainDeploymentPlanRead) -> str:
        return self._render_static_page(
            title="404",
            eyebrow="Page not found",
            message="На этом платежном домене нет страницы по указанному адресу.",
            detail="Рабочие ссылки на оплату формируются автоматически и содержат путь /api/v1/freekassa/pay/<token>. Для нового платежа используйте ссылку из Telegram-бота.",
            domain=plan.domain,
            status_label="Страница не найдена",
            action_label="На главную",
            action_href="/",
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
        return json.dumps(payload, ensure_ascii=False, indent=2) + chr(10)

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
            index_temp = f"{temp_root}/index.html"
            not_found_temp = f"{temp_root}/404.html"
            static_root = self._static_root(plan=plan)

            self._run(client, f"mkdir -p {shlex.quote(temp_root)}", connection=effective_connection)
            self._upload_text(client, nginx_temp, self._build_nginx_config(plan=plan))
            self._upload_text(client, metadata_temp, self._build_deployment_metadata(plan=plan))
            self._upload_text(client, index_temp, self._build_index_page(plan=plan))
            self._upload_text(client, not_found_temp, self._build_not_found_page(plan=plan))
            self._upload_text(
                client,
                readme_temp,
                f"""Managed payment domain reverse proxy for FreeKassa.
Domain: {plan.domain}
Backend API: {plan.backend_api_base_url}
Nginx config: {plan.nginx_config_path}
Static pages: {static_root}
""",
            )

            try:
                self._run(
                    client,
                    (
                        f"mkdir -p {shlex.quote(plan.remote_root)} {shlex.quote(static_root)} && "
                        f"install -m 0644 {shlex.quote(metadata_temp)} {shlex.quote(f'{plan.remote_root}/deployment.json')} && "
                        f"install -m 0644 {shlex.quote(readme_temp)} {shlex.quote(f'{plan.remote_root}/README.txt')} && "
                        f"install -m 0644 {shlex.quote(index_temp)} {shlex.quote(f'{static_root}/index.html')} && "
                        f"install -m 0644 {shlex.quote(not_found_temp)} {shlex.quote(f'{static_root}/404.html')}"
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
