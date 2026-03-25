from __future__ import annotations

import json
import re
import shlex
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit

import paramiko

from app.schemas.site import SiteConnectionPayload, SiteConnectionProbeResponse, SiteDeploymentPlanRead
from app.services.exceptions import ServiceError


@dataclass(frozen=True, slots=True)
class RemoteCommandResult:
    stdout: str
    stderr: str
    exit_status: int


class SiteDeployer:
    default_proxy_port = 5000
    _ansi_escape_pattern = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

    @contextmanager
    def _connect(self, connection: SiteConnectionPayload):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=connection.host.strip(),
                port=connection.port,
                username=connection.username.strip(),
                password=connection.password,
                timeout=20,
                auth_timeout=20,
                banner_timeout=20,
                look_for_keys=False,
                allow_agent=False,
            )
        except paramiko.AuthenticationException as exc:
            raise ServiceError("Не удалось подключиться: неверный логин или пароль", 400) from exc
        except paramiko.SSHException as exc:
            raise ServiceError(f"SSH-подключение завершилось ошибкой: {exc}", 400) from exc
        except OSError as exc:
            raise ServiceError(f"Не удалось подключиться к серверу: {exc}", 400) from exc

        try:
            yield client
        finally:
            client.close()

    def _run(
        self,
        client: paramiko.SSHClient,
        command: str,
        *,
        connection: SiteConnectionPayload,
        use_sudo: bool = False,
        check: bool = True,
    ) -> RemoteCommandResult:
        wrapped = f"bash -lc {shlex.quote(command)}"
        needs_sudo = use_sudo and connection.access_mode == "sudo"
        if needs_sudo:
            wrapped = f"sudo -S -p '' {wrapped}"

        stdin, stdout, stderr = client.exec_command(wrapped, get_pty=needs_sudo)
        if needs_sudo:
            stdin.write(f"{connection.password}\n")
            stdin.flush()

        exit_status = stdout.channel.recv_exit_status()
        result = RemoteCommandResult(
            stdout=stdout.read().decode("utf-8", errors="ignore").strip(),
            stderr=stderr.read().decode("utf-8", errors="ignore").strip(),
            exit_status=exit_status,
        )
        if check and exit_status != 0:
            detail = result.stderr or result.stdout or command
            raise ServiceError(f"Команда на сервере завершилась ошибкой: {detail}", 502)
        return result

    def _upload_text(self, client: paramiko.SSHClient, remote_path: str, content: str) -> None:
        sftp = client.open_sftp()
        try:
            with sftp.file(remote_path, "w") as handle:
                handle.write(content)
        except OSError as exc:
            raise ServiceError(f"Не удалось загрузить файл {remote_path}: {exc}", 502) from exc
        finally:
            sftp.close()

    def _strip_ansi(self, value: str) -> str:
        return self._ansi_escape_pattern.sub("", value or "")

    def _collect_probe(
        self,
        client: paramiko.SSHClient,
        connection: SiteConnectionPayload,
    ) -> SiteConnectionProbeResponse:
        current_user = self._run(client, "whoami", connection=connection).stdout or connection.username
        home_dir = self._run(client, "printf '%s' \"$HOME\"", connection=connection).stdout or "~"
        hostname = self._run(client, "hostname", connection=connection).stdout or connection.host
        kernel = self._run(client, "uname -sr", connection=connection).stdout or "unknown"
        machine = self._run(client, "uname -m", connection=connection).stdout or None
        os_release = self._run(
            client,
            "if [ -r /etc/os-release ]; then . /etc/os-release && printf '%s\\n%s' \"$NAME\" \"$VERSION\"; else printf 'Unknown Linux\\n'; fi",
            connection=connection,
        ).stdout.splitlines()
        python_version_raw = self._run(
            client,
            "python3 --version 2>/dev/null || true",
            connection=connection,
            check=False,
        ).stdout
        package_manager = self._run(
            client,
            "if command -v apt-get >/dev/null 2>&1; then printf 'apt'; "
            "elif command -v dnf >/dev/null 2>&1; then printf 'dnf'; "
            "elif command -v yum >/dev/null 2>&1; then printf 'yum'; "
            "else printf 'unknown'; fi",
            connection=connection,
        ).stdout

        is_root = current_user == "root"
        sudo_available = True if is_root else self._run(
            client,
            "true",
            connection=connection,
            use_sudo=True,
            check=False,
        ).exit_status == 0

        if connection.access_mode == "root" and not is_root:
            raise ServiceError("Для выбранного режима нужен root-доступ", 400)
        if connection.access_mode == "sudo" and not sudo_available:
            raise ServiceError("У пользователя нет рабочего sudo-доступа", 400)

        return SiteConnectionProbeResponse(
            ok=True,
            message="Подключение проверено. Сервер готов к развертыванию сайта.",
            hostname=hostname,
            os_name=os_release[0] if os_release else "Unknown Linux",
            os_version=os_release[1] if len(os_release) > 1 else None,
            kernel=kernel,
            machine=machine,
            python_version=python_version_raw.replace("Python ", "") or None,
            current_user=current_user,
            home_dir=home_dir,
            is_root=is_root,
            sudo_available=sudo_available,
            package_manager=package_manager if package_manager != "unknown" else None,
        )

    def probe_connection(self, connection: SiteConnectionPayload) -> SiteConnectionProbeResponse:
        with self._connect(connection) as client:
            return self._collect_probe(client, connection)

    def _build_remote_app(
        self,
        *,
        rendered_html: str,
        site_name: str,
        telegram_url: str,
        telegram_handle: str,
    ) -> str:
        html_literal = json.dumps(rendered_html, ensure_ascii=False)
        site_name_literal = json.dumps(site_name, ensure_ascii=False)
        telegram_url_literal = json.dumps(telegram_url, ensure_ascii=False)
        telegram_handle_literal = json.dumps(telegram_handle, ensure_ascii=False)
        result_template = json.dumps(
            """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ site_name }} · Конфиг</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --card: rgba(255, 255, 255, 0.94);
      --text: #0f172a;
      --muted: #475569;
      --line: rgba(148, 163, 184, 0.22);
      --accent: #0f766e;
      --accent-bg: rgba(15, 118, 110, 0.1);
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --secondary: #e2e8f0;
      --shadow: 0 20px 60px rgba(15, 23, 42, 0.08);
    }
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      font-family: Inter, system-ui, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(37, 99, 235, 0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(59, 130, 246, 0.12), transparent 24%),
        linear-gradient(180deg, #f8fbff 0%, #eef4fa 100%);
      color: var(--text);
    }
    .wrap {
      max-width: 960px;
      margin: 0 auto;
      padding: 32px 18px 56px;
    }
    .hero,
    .panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
    }
    .hero {
      padding: 30px 24px;
    }
    .panel {
      padding: 24px 22px;
    }
    h1 {
      margin: 0 0 14px;
      font-size: clamp(28px, 5vw, 42px);
      line-height: 1.08;
      letter-spacing: -0.03em;
    }
    h2 {
      margin: 0 0 10px;
      font-size: 20px;
    }
    p {
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }
    .lead {
      max-width: 720px;
      font-size: 18px;
    }
    .reminder {
      margin-top: 14px;
      max-width: 720px;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 22px;
    }
    .btn {
      appearance: none;
      border: none;
      border-radius: 16px;
      padding: 14px 18px;
      background: var(--primary);
      color: #fff;
      text-decoration: none;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.18s ease, transform 0.18s ease;
    }
    .btn:hover {
      background: var(--primary-hover);
      transform: translateY(-1px);
    }
    .btn-secondary {
      background: var(--secondary);
      color: var(--text);
    }
    .btn-secondary:hover {
      background: #cbd5e1;
    }
    .state {
      display: inline-flex;
      align-items: center;
      margin-bottom: 16px;
      padding: 10px 14px;
      border-radius: 999px;
      background: var(--accent-bg);
      color: var(--accent);
      font-size: 14px;
      font-weight: 700;
    }
    .copy-status {
      min-height: 22px;
      margin-top: 12px;
      color: var(--accent);
      font-size: 14px;
      font-weight: 600;
    }
    .meta {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 22px;
    }
    .meta-item {
      padding: 16px 18px;
      border-radius: 20px;
      border: 1px solid rgba(148, 163, 184, 0.16);
      background: rgba(248, 250, 252, 0.92);
    }
    .meta-item span {
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 6px;
    }
    .meta-item strong {
      display: block;
      color: var(--text);
      font-size: 15px;
      word-break: break-word;
    }
    .grid {
      display: grid;
      grid-template-columns: minmax(0, 320px) minmax(0, 1fr);
      gap: 20px;
      margin-top: 20px;
    }
    .qr-hint {
      margin-bottom: 14px;
    }
    .qr-frame {
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 320px;
      padding: 18px;
      border-radius: 24px;
      background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
      border: 1px solid rgba(148, 163, 184, 0.18);
    }
    .qr-frame svg {
      display: block;
      width: 100%;
      max-width: 280px;
      height: auto;
    }
    .qr-fallback {
      color: var(--muted);
      text-align: center;
    }
    .summary-block,
    .config-view {
      width: 100%;
      border: 1px solid rgba(148, 163, 184, 0.26);
      border-radius: 18px;
      background: #f8fafc;
      padding: 16px;
      color: var(--text);
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      font: 14px/1.6 "IBM Plex Mono", ui-monospace, monospace;
    }
    .summary-block {
      margin: 0;
      min-height: 146px;
    }
    .config-view {
      min-height: 146px;
      resize: vertical;
    }
    details {
      margin-top: 18px;
      border-top: 1px solid rgba(148, 163, 184, 0.18);
      padding-top: 18px;
    }
    summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--text);
      list-style: none;
    }
    summary::-webkit-details-marker {
      display: none;
    }
    details[open] summary {
      margin-bottom: 14px;
    }
    @media (max-width: 820px) {
      .grid {
        grid-template-columns: 1fr;
      }
      .qr-frame {
        min-height: 280px;
      }
      .actions {
        flex-direction: column;
      }
      .btn {
        width: 100%;
        justify-content: center;
      }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="state">Конфиг готов</div>
      <h1>Спасибо, что выбрали {{ site_name }}</h1>
      <p class="lead">
        Ваш конфиг уже готов. Ниже можно сразу отсканировать QR-код или скопировать строку подключения в буфер обмена.
      </p>
      <p class="reminder">
        Если удобнее продолжить через Telegram, бот {{ telegram_handle }} остаётся под рукой и доступен по кнопке ниже.
      </p>
      <div class="actions">
        <button class="btn" id="copy-btn" type="button">Скопировать конфиг</button>
        <a class="btn btn-secondary" href="{{ telegram_url }}" rel="noopener noreferrer" target="_blank">Открыть Telegram</a>
        <a class="btn btn-secondary" href="/">Назад на сайт</a>
      </div>
      <div class="copy-status" id="copy-status"></div>
      <div class="meta">
        <div class="meta-item">
          <span>Сервер</span>
          <strong>{{ server_name }}</strong>
        </div>
        <div class="meta-item">
          <span>Канал</span>
          <strong>{{ product_code }}</strong>
        </div>
        <div class="meta-item">
          <span>Действует до</span>
          <strong>{{ expires_at }}</strong>
        </div>
        <div class="meta-item">
          <span>Access ID</span>
          <strong>{{ access_id }}</strong>
        </div>
      </div>
    </section>

    <section class="grid">
      <article class="panel">
        <h2>QR-код</h2>
        <p class="qr-hint">Отсканируйте его в приложении, которое умеет импортировать VLESS URI.</p>
        <div class="qr-frame">
          {% if qr_svg %}
            {{ qr_svg | safe }}
          {% else %}
            <div class="qr-fallback">QR-код временно недоступен. Используйте кнопку копирования ниже.</div>
          {% endif %}
        </div>
      </article>

      <article class="panel">
        <h2>Что вы получили</h2>
        <pre class="summary-block">{{ config_text }}</pre>
        <details>
          <summary>Показать полный конфиг</summary>
          <textarea class="config-view" readonly>{{ config_uri }}</textarea>
        </details>
      </article>
    </section>
  </main>
  <script>
    const copyBtn = document.getElementById("copy-btn");
    const copyStatus = document.getElementById("copy-status");
    const configValue = {{ config_uri | tojson }};

    async function copyConfig() {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(configValue);
        return;
      }
      const temp = document.createElement("textarea");
      temp.value = configValue;
      temp.setAttribute("readonly", "");
      temp.style.position = "absolute";
      temp.style.left = "-9999px";
      document.body.appendChild(temp);
      temp.select();
      document.execCommand("copy");
      document.body.removeChild(temp);
    }

    if (copyBtn) {
      copyBtn.addEventListener("click", async () => {
        try {
          await copyConfig();
          copyBtn.textContent = "Скопировано";
          if (copyStatus) {
            copyStatus.textContent = "Конфиг скопирован в буфер обмена.";
          }
          setTimeout(() => {
            copyBtn.textContent = "Скопировать конфиг";
          }, 1600);
        } catch (_) {
          if (copyStatus) {
            copyStatus.textContent = "Не удалось скопировать автоматически. Откройте полный конфиг и скопируйте его вручную.";
          }
        }
      });
    }
  </script>
</body>
</html>
            """.strip(),
            ensure_ascii=False,
        )
        error_template = json.dumps(
            """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ site_name }} · Ошибка</title>
  <style>
    body {
      margin: 0;
      font-family: Inter, system-ui, sans-serif;
      background: linear-gradient(180deg, #f8fbff 0%, #eef4fa 100%);
      color: #0f172a;
    }
    .wrap {
      max-width: 760px;
      margin: 0 auto;
      padding: 32px 18px 56px;
    }
    .card {
      background: rgba(255, 255, 255, 0.94);
      border: 1px solid rgba(239, 68, 68, 0.18);
      border-radius: 28px;
      box-shadow: 0 20px 60px rgba(15, 23, 42, 0.08);
      padding: 30px 24px;
    }
    h1 {
      margin: 0 0 12px;
      font-size: clamp(28px, 5vw, 40px);
    }
    p {
      margin: 0;
      color: #475569;
      line-height: 1.7;
    }
    .error {
      margin-top: 18px;
      padding: 16px;
      border-radius: 18px;
      background: #fef2f2;
      color: #991b1b;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-top: 18px;
      padding: 14px 18px;
      border-radius: 16px;
      background: #0f172a;
      color: #fff;
      text-decoration: none;
      font-weight: 700;
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>{{ site_name }}</h1>
      <p>Не удалось выдать конфиг с сайта.</p>
      <div class="error">{{ detail }}</div>
      <a class="btn" href="/">Вернуться</a>
    </section>
  </main>
</body>
</html>
            """.strip(),
            ensure_ascii=False,
        )
        return (
            "from __future__ import annotations\n\n"
            "import io\n"
            "import logging\n"
            "import os\n"
            "import secrets\n\n"
            "import httpx\n"
            "import qrcode\n"
            "import qrcode.image.svg\n"
            "from flask import Flask, Response, jsonify, make_response, render_template_string, request\n\n"
            f"LANDING_HTML = {html_literal}\n"
            f"SITE_NAME = {site_name_literal}\n"
            f"TELEGRAM_URL = {telegram_url_literal}\n"
            f"TELEGRAM_HANDLE = {telegram_handle_literal}\n"
            f"RESULT_TEMPLATE = {result_template}\n"
            f"ERROR_TEMPLATE = {error_template}\n"
            "COOKIE_NAME = 'site_visitor_token'\n"
            "BACKEND_BASE_URL = os.environ['BACKEND_BASE_URL'].rstrip('/')\n"
            "SITE_RUNTIME_TOKEN = os.environ['SITE_RUNTIME_TOKEN']\n"
            "SITE_CODE = os.environ['SITE_CODE']\n\n"
            "class SiteRuntimeError(RuntimeError):\n"
            "    def __init__(self, message: str, status_code: int) -> None:\n"
            "        super().__init__(message)\n"
            "        self.status_code = status_code\n\n"
            "logger = logging.getLogger(__name__)\n\n"
            "app = Flask(__name__)\n\n"
            "def _ensure_visitor_token() -> tuple[str, bool]:\n"
            "    token = request.cookies.get(COOKIE_NAME)\n"
            "    if token:\n"
            "        return token, False\n"
            "    return secrets.token_urlsafe(24), True\n\n"
            "def _is_https_request() -> bool:\n"
            "    forwarded_proto = request.headers.get('X-Forwarded-Proto', '')\n"
            "    if forwarded_proto:\n"
            "        return forwarded_proto.split(',')[0].strip().lower() == 'https'\n"
            "    return request.is_secure\n\n"
            "def _finalize(response, token: str, created: bool):\n"
            "    if created:\n"
            "        response.set_cookie(\n"
            "            COOKIE_NAME,\n"
            "            token,\n"
            "            max_age=31536000,\n"
            "            httponly=True,\n"
            "            secure=_is_https_request(),\n"
            "            samesite='Lax',\n"
            "        )\n"
            "    response.headers.setdefault('Cache-Control', 'no-store')\n"
            "    return response\n\n"
            "def _get_client_ip() -> str | None:\n"
            "    forwarded = request.headers.get('X-Forwarded-For', '')\n"
            "    if forwarded:\n"
            "        return forwarded.split(',')[0].strip()\n"
            "    return request.headers.get('X-Real-IP') or request.remote_addr\n\n"
            "def _build_qr_svg(value: str) -> str:\n"
            "    qr = qrcode.QRCode(box_size=8, border=2)\n"
            "    qr.add_data(value)\n"
            "    qr.make(fit=True)\n"
            "    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)\n"
            "    buffer = io.BytesIO()\n"
            "    image.save(buffer)\n"
            "    return buffer.getvalue().decode('utf-8')\n\n"
            "def _validate_config_payload(payload: dict) -> dict:\n"
            "    required_fields = ('access_id', 'config_uri', 'config_text', 'expires_at', 'product_code', 'server_name')\n"
            "    missing = [field for field in required_fields if field not in payload]\n"
            "    if missing:\n"
            "        raise SiteRuntimeError(f\"Backend вернул неполный ответ: отсутствуют поля {', '.join(missing)}\", 502)\n"
            "    return payload\n\n"
            "def _request_config(visitor_token: str) -> dict:\n"
            "    try:\n"
            "        with httpx.Client(timeout=30.0) as client:\n"
            "            response = client.post(\n"
            "                f'{BACKEND_BASE_URL}/site-runtime/request-config',\n"
            "                headers={'X-Site-Token': SITE_RUNTIME_TOKEN},\n"
            "                json={\n"
            "                    'site_code': SITE_CODE,\n"
            "                    'visitor_token': visitor_token,\n"
            "                    'client_ip': _get_client_ip(),\n"
            "                    'user_agent': request.headers.get('User-Agent'),\n"
            "                },\n"
            "            )\n"
            "    except httpx.HTTPError as exc:\n"
            "        logger.exception('Не удалось запросить конфиг у backend %s', BACKEND_BASE_URL)\n"
            "        raise SiteRuntimeError(f'Не удалось связаться с backend: {exc}', 502) from exc\n"
            "    content_type = response.headers.get('content-type', '')\n"
            "    try:\n"
            "        payload = response.json() if content_type.startswith('application/json') else {'detail': response.text}\n"
            "    except ValueError as exc:\n"
            "        logger.exception('Backend вернул невалидный JSON для сайта %s', SITE_CODE)\n"
            "        raise SiteRuntimeError('Backend вернул невалидный ответ', 502) from exc\n"
            "    if response.status_code >= 400:\n"
            "        detail = payload.get('detail') if isinstance(payload, dict) else None\n"
            "        raise SiteRuntimeError(detail or 'Не удалось получить конфиг', response.status_code)\n"
            "    return _validate_config_payload(payload)\n\n"
            "@app.get('/')\n"
            "def index() -> Response:\n"
            "    token, created = _ensure_visitor_token()\n"
            "    response = make_response(Response(LANDING_HTML, mimetype='text/html; charset=utf-8'))\n"
            "    return _finalize(response, token, created)\n\n"
            "@app.get('/config')\n"
            "def config_page():\n"
            "    token, created = _ensure_visitor_token()\n"
            "    try:\n"
            "        qr_svg = ''\n"
            "        payload = _request_config(token)\n"
            "        if payload.get('config_uri'):\n"
            "            qr_svg = _build_qr_svg(payload['config_uri'])\n"
            "        response = make_response(render_template_string(\n"
            "            RESULT_TEMPLATE,\n"
            "            site_name=SITE_NAME,\n"
            "            telegram_url=TELEGRAM_URL,\n"
            "            telegram_handle=TELEGRAM_HANDLE,\n"
            "            access_id=payload['access_id'],\n"
            "            config_uri=payload['config_uri'],\n"
            "            config_text=payload['config_text'],\n"
            "            qr_svg=qr_svg,\n"
            "            expires_at=payload.get('expires_at_label', payload['expires_at']),\n"
            "            product_code=payload['product_code'],\n"
            "            server_name=payload['server_name'],\n"
            "        ))\n"
            "    except SiteRuntimeError as exc:\n"
            "        response = make_response(render_template_string(ERROR_TEMPLATE, site_name=SITE_NAME, detail=str(exc)), exc.status_code)\n"
            "    except Exception as exc:\n"
            "        logger.exception('Не удалось построить страницу /config для сайта %s', SITE_CODE)\n"
            "        response = make_response(render_template_string(ERROR_TEMPLATE, site_name=SITE_NAME, detail=f'Внутренняя ошибка страницы конфигурации: {exc}'), 500)\n"
            "    return _finalize(response, token, created)\n\n"
            "@app.post('/api/request-config')\n"
            "def api_request_config():\n"
            "    token, created = _ensure_visitor_token()\n"
            "    try:\n"
            "        response = make_response(jsonify(_request_config(token)))\n"
            "    except SiteRuntimeError as exc:\n"
            "        response = make_response(jsonify({'detail': str(exc)}), exc.status_code)\n"
            "    except Exception as exc:\n"
            "        logger.exception('Не удалось обработать /api/request-config для сайта %s', SITE_CODE)\n"
            "        response = make_response(jsonify({'detail': f'Внутренняя ошибка страницы конфигурации: {exc}'}), 500)\n"
            "    return _finalize(response, token, created)\n\n"
            "@app.get('/health')\n"
            "def health() -> dict[str, str]:\n"
            "    return {'status': 'ok'}\n"
        )

    def _build_requirements(self) -> str:
        return "Flask==3.1.0\ngunicorn==23.0.0\nhttpx==0.28.1\nqrcode==8.2\n"

    def _resolve_service_user(
        self,
        client: paramiko.SSHClient,
        connection: SiteConnectionPayload,
    ) -> tuple[str, str]:
        for candidate in ("www-data", "nginx"):
            result = self._run(
                client,
                f"id -u {shlex.quote(candidate)} >/dev/null 2>&1",
                connection=connection,
                check=False,
            )
            if result.exit_status == 0:
                return candidate, candidate
        return connection.username.strip(), connection.username.strip()

    def _build_systemd_unit(
        self,
        *,
        plan: SiteDeploymentPlanRead,
        service_user: str,
        service_group: str,
        backend_base_url: str,
        site_runtime_token: str,
    ) -> str:
        venv_dir = f"{plan.remote_root}/venv"
        return (
            "[Unit]\n"
            f"Description=Managed site {plan.service_name}\n"
            "After=network.target\n\n"
            "[Service]\n"
            f"User={service_user}\n"
            f"Group={service_group}\n"
            f"WorkingDirectory={plan.app_dir}\n"
            f"Environment=\"PATH={venv_dir}/bin\"\n"
            f"Environment=\"BACKEND_BASE_URL={backend_base_url}\"\n"
            f"Environment=\"SITE_RUNTIME_TOKEN={site_runtime_token}\"\n"
            f"Environment=\"SITE_CODE={plan.site_code}\"\n"
            f"ExecStart={venv_dir}/bin/gunicorn --workers 2 --bind 127.0.0.1:{plan.proxy_port} app:app\n"
            "Restart=always\n"
            "RestartSec=3\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )

    def _build_cloudflared_launcher(
        self,
        *,
        plan: SiteDeploymentPlanRead,
        backend_base_url: str,
        site_runtime_token: str,
    ) -> str:
        if not plan.cloudflare_url_file or not plan.cloudflare_log_file:
            raise ServiceError("Для Cloudflare Tunnel не подготовлены служебные пути", 500)
        report_url = f"{backend_base_url.rstrip('/')}/site-runtime/report-public-url"
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n\n"
            f"URL_FILE={shlex.quote(plan.cloudflare_url_file)}\n"
            f"LOG_FILE={shlex.quote(plan.cloudflare_log_file)}\n"
            f"SITE_CODE={shlex.quote(plan.site_code)}\n"
            f"SITE_RUNTIME_TOKEN={shlex.quote(site_runtime_token)}\n"
            f"REPORT_URL={shlex.quote(report_url)}\n"
            f"TARGET_URL={shlex.quote(f'http://127.0.0.1:{plan.proxy_port}')}\n\n"
            "mkdir -p \"$(dirname \"$URL_FILE\")\"\n"
            ": > \"$LOG_FILE\"\n"
            "rm -f \"$URL_FILE\"\n\n"
            "TUNNEL_TRANSPORT_PROTOCOL=http2 cloudflared tunnel --no-autoupdate --url \"$TARGET_URL\" 2>&1 | tee -a \"$LOG_FILE\" | while IFS= read -r line; do\n"
            "  printf '%s\\n' \"$line\"\n"
            "  url=$(printf '%s\\n' \"$line\" | sed -nE 's#.*(https://[A-Za-z0-9.-]+\\.trycloudflare\\.com).*#\\1#p' | head -n 1)\n"
            "  if [ -n \"$url\" ]; then\n"
            "    printf '%s' \"$url\" > \"$URL_FILE\"\n"
            "    curl -fsS -X POST \\\n"
            "      -H 'Content-Type: application/json' \\\n"
            "      -H \"X-Site-Token: $SITE_RUNTIME_TOKEN\" \\\n"
            "      --data \"{\\\"site_code\\\":\\\"$SITE_CODE\\\",\\\"public_url\\\":\\\"$url\\\"}\" \\\n"
            "      \"$REPORT_URL\" >/dev/null || true\n"
            "  fi\n"
            "done\n"
        )

    def _build_cloudflared_systemd_unit(
        self,
        *,
        plan: SiteDeploymentPlanRead,
        service_user: str,
        service_group: str,
    ) -> str:
        launcher_path = f"{plan.remote_root}/bin/start-cloudflared.sh"
        return (
            "[Unit]\n"
            f"Description=Cloudflare quick tunnel for {plan.service_name}\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n"
            f"Requires={plan.service_name}.service\n"
            f"After={plan.service_name}.service\n\n"
            "[Service]\n"
            f"User={service_user}\n"
            f"Group={service_group}\n"
            f"WorkingDirectory={plan.remote_root}\n"
            f"ExecStart={launcher_path}\n"
            "Restart=always\n"
            "RestartSec=3\n"
            "NoNewPrivileges=true\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )

    def _build_http_nginx_config(self, *, plan: SiteDeploymentPlanRead) -> str:
        return (
            "server {\n"
            "    listen 80;\n"
            f"    server_name {plan.server_name};\n\n"
            "    location / {\n"
            f"        proxy_pass http://127.0.0.1:{plan.proxy_port};\n"
            "        proxy_set_header Host $host;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto $scheme;\n"
            "        proxy_read_timeout 60s;\n"
            "    }\n"
            "}\n"
        )

    def _build_https_nginx_config(
        self,
        *,
        plan: SiteDeploymentPlanRead,
        certificate_path: str,
        private_key_path: str,
    ) -> str:
        return (
            "server {\n"
            "    listen 80;\n"
            f"    server_name {plan.server_name};\n"
            "    return 301 https://$host$request_uri;\n"
            "}\n\n"
            "server {\n"
            "    listen 443 ssl http2;\n"
            f"    server_name {plan.server_name};\n\n"
            f"    ssl_certificate {certificate_path};\n"
            f"    ssl_certificate_key {private_key_path};\n"
            "    ssl_session_cache shared:SSL:10m;\n"
            "    ssl_session_timeout 10m;\n\n"
            "    location / {\n"
            f"        proxy_pass http://127.0.0.1:{plan.proxy_port};\n"
            "        proxy_set_header Host $host;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto https;\n"
            "        proxy_read_timeout 60s;\n"
            "    }\n"
            "}\n"
        )

    def _ensure_base_packages(
        self,
        client: paramiko.SSHClient,
        connection: SiteConnectionPayload,
        package_manager: str | None,
        *,
        include_nginx: bool,
        include_certbot: bool,
    ) -> None:
        if package_manager == "apt":
            packages = ["python3", "python3-venv", "python3-pip", "curl", "ca-certificates", "openssl"]
            if include_nginx:
                packages.append("nginx")
            if include_certbot:
                packages.extend(["certbot", "python3-certbot-nginx"])
            self._run(
                client,
                "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y " + " ".join(packages),
                connection=connection,
                use_sudo=True,
            )
            return

        if package_manager in {"dnf", "yum"}:
            packages = ["python3", "python3-pip", "curl", "ca-certificates", "openssl"]
            if include_nginx:
                packages.append("nginx")
            if include_certbot:
                packages.extend(["certbot", "python3-certbot-nginx"])
            self._run(
                client,
                f"{package_manager} install -y " + " ".join(packages),
                connection=connection,
                use_sudo=True,
            )
            return

        raise ServiceError("На сервере не найден поддерживаемый пакетный менеджер (apt/dnf/yum)", 400)

    def _map_cloudflared_arch(self, machine: str | None) -> str:
        normalized = (machine or "").strip().lower()
        mapping = {
            "x86_64": "amd64",
            "amd64": "amd64",
            "aarch64": "arm64",
            "arm64": "arm64",
            "armv7l": "arm",
            "armhf": "arm",
        }
        arch = mapping.get(normalized)
        if not arch:
            raise ServiceError(f"Архитектура {machine or 'unknown'} не поддерживается для cloudflared", 400)
        return arch

    def _ensure_cloudflared_binary(
        self,
        client: paramiko.SSHClient,
        connection: SiteConnectionPayload,
        machine: str | None,
    ) -> None:
        existing = self._run(
            client,
            "command -v cloudflared >/dev/null 2>&1",
            connection=connection,
            check=False,
        )
        if existing.exit_status == 0:
            return

        arch = self._map_cloudflared_arch(machine)
        temp_binary = f"/tmp/cloudflared-{arch}"
        download_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        self._run(
            client,
            f"curl -fsSL {shlex.quote(download_url)} -o {shlex.quote(temp_binary)}",
            connection=connection,
            use_sudo=True,
        )
        self._run(
            client,
            (
                f"install -m 0755 {shlex.quote(temp_binary)} /usr/local/bin/cloudflared && "
                f"rm -f {shlex.quote(temp_binary)}"
            ),
            connection=connection,
            use_sudo=True,
        )

    def _normalize_cloudflare_public_url(self, raw_url: str) -> str:
        normalized_url = raw_url.strip()
        parsed = urlsplit(normalized_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not hostname.endswith(".trycloudflare.com"):
            raise ServiceError("Ожидался HTTPS-адрес Cloudflare Quick Tunnel", 400)
        return normalized_url

    def read_cloudflare_public_url(
        self,
        *,
        connection: SiteConnectionPayload,
        plan: SiteDeploymentPlanRead,
    ) -> dict:
        if plan.publish_mode != "cloudflare_tunnel":
            raise ServiceError("Обновление URL доступно только для Cloudflare Tunnel", 409)
        if not plan.cloudflare_url_file or not plan.cloudflare_log_file:
            raise ServiceError("Для Cloudflare Tunnel не описаны служебные пути", 500)

        with self._connect(connection) as client:
            probe = self._collect_probe(client, connection)
            effective_connection = (
                connection.model_copy(update={"access_mode": "root"})
                if probe.is_root
                else connection
            )
            cloudflare_service_name = f"{plan.service_name}-cloudflared"
            active_result = self._run(
                client,
                f"systemctl show {shlex.quote(cloudflare_service_name)} --property=ActiveState --value",
                connection=effective_connection,
                use_sudo=True,
                check=False,
            )
            active_state = self._strip_ansi(active_result.stdout).strip().splitlines()[-1].strip() if active_result.stdout.strip() else ""
            if active_result.exit_status != 0 or active_state != "active":
                status_result = self._run(
                    client,
                    f"SYSTEMD_COLORS=0 systemctl status {shlex.quote(cloudflare_service_name)} --no-pager -l",
                    connection=effective_connection,
                    use_sudo=True,
                    check=False,
                )
                detail = self._strip_ansi(status_result.stdout or status_result.stderr or "Cloudflare Tunnel не запущен")
                raise ServiceError(f"Cloudflare Tunnel не активен: {detail}", 502)

            url_result = self._run(
                client,
                f"cat {shlex.quote(plan.cloudflare_url_file)}",
                connection=effective_connection,
                use_sudo=True,
                check=False,
            )
            raw_url = url_result.stdout.strip().splitlines()[-1].strip() if url_result.stdout.strip() else ""
            if not raw_url:
                log_result = self._run(
                    client,
                    f"tail -n 40 {shlex.quote(plan.cloudflare_log_file)}",
                    connection=effective_connection,
                    use_sudo=True,
                    check=False,
                )
                detail = (
                    log_result.stdout
                    or log_result.stderr
                    or "Cloudflare Tunnel не записал текущий trycloudflare URL"
                )
                raise ServiceError(f"Cloudflare Tunnel не выдал публичный URL: {detail}", 502)
            public_url = self._normalize_cloudflare_public_url(raw_url)
            probe_result = self._run(
                client,
                f"curl -sSIL -o /dev/null -w '%{{http_code}}' --max-time 15 {shlex.quote(public_url)}",
                connection=effective_connection,
                check=False,
            )
            status_code = (probe_result.stdout or "").strip()
            if status_code == "530":
                log_result = self._run(
                    client,
                    f"tail -n 40 {shlex.quote(plan.cloudflare_log_file)}",
                    connection=effective_connection,
                    use_sudo=True,
                    check=False,
                )
                detail = self._strip_ansi(log_result.stdout or log_result.stderr or "trycloudflare URL устарел")
                raise ServiceError(
                    "Cloudflare Quick Tunnel запущен, но текущий trycloudflare URL уже не привязан к edge. "
                    f"Последние логи cloudflared: {detail}",
                    502,
                )

            return {
                "public_url": public_url,
                "connection_snapshot": probe.model_dump(),
            }

    def deploy(
        self,
        *,
        connection: SiteConnectionPayload,
        plan: SiteDeploymentPlanRead,
        rendered_html: str,
        site_name: str,
        telegram_url: str,
        telegram_handle: str,
        backend_base_url: str,
        site_runtime_token: str,
    ) -> dict:
        warnings = list(plan.warnings)

        with self._connect(connection) as client:
            probe = self._collect_probe(client, connection)
            effective_connection = (
                connection.model_copy(update={"access_mode": "root"})
                if probe.is_root
                else connection
            )
            package_manager = probe.package_manager
            self._ensure_base_packages(
                client,
                effective_connection,
                package_manager,
                include_nginx=plan.publish_mode != "cloudflare_tunnel",
                include_certbot=plan.publish_mode == "domain",
            )
            if plan.publish_mode == "cloudflare_tunnel":
                self._ensure_cloudflared_binary(client, effective_connection, probe.machine)

            temp_root = f"{probe.home_dir.rstrip('/')}/.xray-site-deploy/{plan.site_code}"
            app_py_temp = f"{temp_root}/app.py"
            requirements_temp = f"{temp_root}/requirements.txt"
            systemd_temp = f"{temp_root}/{plan.service_name}.service"
            nginx_temp = f"{temp_root}/{plan.service_name}.conf"
            launcher_temp = f"{temp_root}/start-cloudflared.sh"
            tunnel_unit_temp = f"{temp_root}/{plan.service_name}-cloudflared.service"

            self._run(client, f"mkdir -p {shlex.quote(temp_root)}", connection=effective_connection)
            self._upload_text(
                client,
                app_py_temp,
                self._build_remote_app(
                    rendered_html=rendered_html,
                    site_name=site_name,
                    telegram_url=telegram_url,
                    telegram_handle=telegram_handle,
                ),
            )
            self._upload_text(client, requirements_temp, self._build_requirements())

            service_user, service_group = self._resolve_service_user(client, effective_connection)
            systemd_unit = self._build_systemd_unit(
                plan=plan,
                service_user=service_user,
                service_group=service_group,
                backend_base_url=backend_base_url,
                site_runtime_token=site_runtime_token,
            )
            self._upload_text(client, systemd_temp, systemd_unit)
            if plan.publish_mode == "cloudflare_tunnel":
                if not plan.cloudflare_unit_path:
                    raise ServiceError("Для Cloudflare Tunnel не указан systemd unit", 500)
                self._upload_text(
                    client,
                    launcher_temp,
                    self._build_cloudflared_launcher(
                        plan=plan,
                        backend_base_url=backend_base_url,
                        site_runtime_token=site_runtime_token,
                    ),
                )
                self._upload_text(
                    client,
                    tunnel_unit_temp,
                    self._build_cloudflared_systemd_unit(
                        plan=plan,
                        service_user=service_user,
                        service_group=service_group,
                    ),
                )
            else:
                self._upload_text(client, nginx_temp, self._build_http_nginx_config(plan=plan))

            public_url = plan.public_url
            ssl_mode = plan.ssl_mode
            cloudflare_service_name = f"{plan.service_name}-cloudflared"

            try:
                self._run(
                    client,
                    (
                        f"mkdir -p {shlex.quote(plan.remote_root)} "
                        f"{shlex.quote(plan.app_dir)} "
                        f"{shlex.quote(f'{plan.remote_root}/bin')} "
                        f"{shlex.quote(f'{plan.remote_root}/run')}"
                    ),
                    connection=effective_connection,
                    use_sudo=True,
                )
                self._run(
                    client,
                    (
                        f"install -m 0644 {shlex.quote(app_py_temp)} {shlex.quote(plan.app_dir)}/app.py && "
                        f"install -m 0644 {shlex.quote(requirements_temp)} {shlex.quote(plan.app_dir)}/requirements.txt && "
                        f"python3 -m venv {shlex.quote(plan.remote_root)}/venv && "
                        f"{shlex.quote(plan.remote_root)}/venv/bin/pip install --upgrade pip wheel && "
                        f"{shlex.quote(plan.remote_root)}/venv/bin/pip install -r {shlex.quote(plan.app_dir)}/requirements.txt && "
                        f"chown -R {shlex.quote(service_user)}:{shlex.quote(service_group)} {shlex.quote(plan.remote_root)} && "
                        f"chmod -R u=rwX,go=rX {shlex.quote(plan.remote_root)}"
                    ),
                    connection=effective_connection,
                    use_sudo=True,
                )
                self._run(
                    client,
                    f"install -m 0644 {shlex.quote(systemd_temp)} {shlex.quote(plan.systemd_unit_path)}",
                    connection=effective_connection,
                    use_sudo=True,
                )
                if plan.publish_mode == "cloudflare_tunnel":
                    if not plan.cloudflare_unit_path or not plan.cloudflare_url_file or not plan.cloudflare_log_file:
                        raise ServiceError("Cloudflare Tunnel не до конца описан в плане развертывания", 500)
                    self._run(
                        client,
                        (
                            f"install -m 0755 {shlex.quote(launcher_temp)} {shlex.quote(f'{plan.remote_root}/bin/start-cloudflared.sh')} && "
                            f"install -m 0644 {shlex.quote(tunnel_unit_temp)} {shlex.quote(plan.cloudflare_unit_path)}"
                        ),
                        connection=effective_connection,
                        use_sudo=True,
                    )
                    self._run(
                        client,
                        (
                            "systemctl daemon-reload && "
                            f"systemctl enable --now {shlex.quote(plan.service_name)} && "
                            f"systemctl enable --now {shlex.quote(cloudflare_service_name)}"
                        ),
                        connection=effective_connection,
                        use_sudo=True,
                    )
                    url_result = self._run(
                        client,
                        (
                            "for attempt in $(seq 1 45); do "
                            f"if [ -s {shlex.quote(plan.cloudflare_url_file)} ]; then "
                            f"cat {shlex.quote(plan.cloudflare_url_file)}; exit 0; "
                            "fi; sleep 1; done; exit 1"
                        ),
                        connection=effective_connection,
                        use_sudo=True,
                        check=False,
                    )
                    public_url = url_result.stdout.strip().splitlines()[-1].strip() if url_result.stdout.strip() else ""
                    if not public_url:
                        status_result = self._run(
                            client,
                            f"systemctl status {shlex.quote(cloudflare_service_name)} --no-pager -l",
                            connection=effective_connection,
                            use_sudo=True,
                            check=False,
                        )
                        log_result = self._run(
                            client,
                            f"tail -n 40 {shlex.quote(plan.cloudflare_log_file)}",
                            connection=effective_connection,
                            use_sudo=True,
                            check=False,
                        )
                        detail = (
                            log_result.stdout
                            or log_result.stderr
                            or status_result.stdout
                            or status_result.stderr
                            or "Cloudflare Tunnel не выдал публичный URL"
                        )
                        raise ServiceError(f"Cloudflare Tunnel не выдал публичный URL: {detail}", 502)
                else:
                    if not plan.nginx_config_path:
                        raise ServiceError("Для nginx-режима не указан путь конфига", 500)
                    self._run(
                        client,
                        f"install -m 0644 {shlex.quote(nginx_temp)} {shlex.quote(plan.nginx_config_path)}",
                        connection=effective_connection,
                        use_sudo=True,
                    )
                    self._run(
                        client,
                        (
                            "systemctl daemon-reload && "
                            f"systemctl enable --now {shlex.quote(plan.service_name)} && "
                            "systemctl enable --now nginx && "
                            "nginx -t && systemctl reload nginx"
                        ),
                        connection=effective_connection,
                        use_sudo=True,
                    )

                    certificate_path = f"/etc/ssl/certs/{plan.service_name}.crt"
                    private_key_path = f"/etc/ssl/private/{plan.service_name}.key"
                    if plan.publish_mode == "domain":
                        certbot = self._run(
                            client,
                            (
                                "certbot --nginx --redirect --non-interactive --agree-tos "
                                "--register-unsafely-without-email "
                                f"-d {shlex.quote(plan.server_name)}"
                            ),
                            connection=effective_connection,
                            use_sudo=True,
                            check=False,
                        )
                        if certbot.exit_status != 0:
                            ssl_mode = "self-signed"
                            warnings.append(
                                "Let's Encrypt не удалось выпустить автоматически. Развернут self-signed сертификат."
                            )

                    if ssl_mode == "self-signed":
                        self._run(
                            client,
                            (
                                f"openssl req -x509 -nodes -days 365 -newkey rsa:2048 "
                                f"-keyout {shlex.quote(private_key_path)} "
                                f"-out {shlex.quote(certificate_path)} "
                                f"-subj /CN={shlex.quote(plan.server_name)}"
                            ),
                            connection=effective_connection,
                            use_sudo=True,
                        )
                        self._upload_text(
                            client,
                            nginx_temp,
                            self._build_https_nginx_config(
                                plan=plan,
                                certificate_path=certificate_path,
                                private_key_path=private_key_path,
                            ),
                        )
                        self._run(
                            client,
                            f"install -m 0644 {shlex.quote(nginx_temp)} {shlex.quote(plan.nginx_config_path)}",
                            connection=effective_connection,
                            use_sudo=True,
                        )
                        self._run(
                            client,
                            "nginx -t && systemctl reload nginx",
                            connection=effective_connection,
                            use_sudo=True,
                        )
            finally:
                self._run(
                    client,
                    f"rm -rf {shlex.quote(temp_root)}",
                    connection=effective_connection,
                    check=False,
                )

        return {
            "public_url": public_url,
            "ssl_mode": ssl_mode,
            "connection_snapshot": probe.model_dump(),
            "deployment_snapshot": {
                **plan.model_dump(),
                "public_url": public_url,
                "cloudflare_public_url": public_url if plan.publish_mode == "cloudflare_tunnel" else None,
                "backend_base_url": backend_base_url,
                "ssl_mode": ssl_mode,
                "warnings": warnings,
                "service_user": service_user,
                "service_group": service_group,
                "cloudflare_service_name": cloudflare_service_name if plan.publish_mode == "cloudflare_tunnel" else None,
            },
        }

    def remove(
        self,
        *,
        connection: SiteConnectionPayload,
        plan: SiteDeploymentPlanRead,
    ) -> dict:
        warnings: list[str] = []

        with self._connect(connection) as client:
            probe = self._collect_probe(client, connection)
            effective_connection = (
                connection.model_copy(update={"access_mode": "root"})
                if probe.is_root
                else connection
            )
            cloudflare_service_name = f"{plan.service_name}-cloudflared"

            self._run(
                client,
                f"systemctl disable --now {shlex.quote(plan.service_name)} >/dev/null 2>&1 || true",
                connection=effective_connection,
                use_sudo=True,
                check=False,
            )
            self._run(
                client,
                f"rm -f {shlex.quote(plan.systemd_unit_path)}",
                connection=effective_connection,
                use_sudo=True,
                check=False,
            )

            if plan.publish_mode == "cloudflare_tunnel" and plan.cloudflare_unit_path:
                self._run(
                    client,
                    f"systemctl disable --now {shlex.quote(cloudflare_service_name)} >/dev/null 2>&1 || true",
                    connection=effective_connection,
                    use_sudo=True,
                    check=False,
                )
                self._run(
                    client,
                    f"rm -f {shlex.quote(plan.cloudflare_unit_path)}",
                    connection=effective_connection,
                    use_sudo=True,
                    check=False,
                )

            if plan.nginx_config_path:
                self._run(
                    client,
                    f"rm -f {shlex.quote(plan.nginx_config_path)}",
                    connection=effective_connection,
                    use_sudo=True,
                    check=False,
                )

            if plan.ssl_mode == "self-signed":
                certificate_path = f"/etc/ssl/certs/{plan.service_name}.crt"
                private_key_path = f"/etc/ssl/private/{plan.service_name}.key"
                self._run(
                    client,
                    f"rm -f {shlex.quote(certificate_path)} {shlex.quote(private_key_path)}",
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
            self._run(
                client,
                "systemctl daemon-reload >/dev/null 2>&1 || true",
                connection=effective_connection,
                use_sudo=True,
                check=False,
            )

            if plan.nginx_config_path:
                nginx_reload = self._run(
                    client,
                    "if command -v nginx >/dev/null 2>&1; then nginx -t && systemctl reload nginx; fi",
                    connection=effective_connection,
                    use_sudo=True,
                    check=False,
                )
                if nginx_reload.exit_status != 0:
                    detail = nginx_reload.stderr or nginx_reload.stdout or "nginx не подтвердил reload"
                    warnings.append(f"Nginx не удалось перезагрузить после удаления сайта: {detail}")

        return {
            "deleted_from_server": True,
            "warnings": warnings,
            "connection_snapshot": probe.model_dump(),
        }
