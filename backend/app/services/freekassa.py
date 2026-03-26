from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from html import escape
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.security import decrypt_secret, secure_compare
from app.db.session import SessionLocal
from app.schemas.freekassa import (
    FreeKassaConfigRead,
    FreeKassaEndpointRead,
    FreeKassaEndpointsRead,
    FreeKassaNotificationRead,
)
from app.services.exceptions import ServiceError


class FreeKassaService:
    classic_sbp_method_id = 42
    api_sbp_method_id = 44
    payment_method_labels = {
        12: "МИР",
        13: "Онлайн банк",
        36: "Card RUB API",
        37: "Google Pay",
        38: "Apple Pay",
        42: "СБП",
        44: "СБП (API)",
    }
    router_prefix = "/freekassa"
    notification_path = "/notify"
    success_path = "/success"
    failure_path = "/fail"
    payment_redirect_path = "/pay"
    api_base_url = "https://api.fk.life/v1"
    checkout_base_url = "https://pay.fk.money/"

    def __init__(self, db: Session | None = None) -> None:
        self.settings = get_settings()
        self.db = db

    def _load_runtime_config(self, *, record=None) -> dict[str, object]:
        local_db: Session | None = None
        try:
            current_record = record
            if current_record is None:
                db = self.db
                if db is None:
                    local_db = SessionLocal()
                    db = local_db
                from app.repositories.system_settings import SystemSettingsRepository

                current_record = SystemSettingsRepository(db).get()

            return {
                "shop_id": current_record.freekassa_shop_id if current_record else None,
                "public_url": (
                    current_record.freekassa_public_url
                    or current_record.public_app_url
                    if current_record
                    else None
                ),
                "secret_word": decrypt_secret(current_record.freekassa_secret_word_encrypted) if current_record else None,
                "api_key": decrypt_secret(current_record.freekassa_api_key_encrypted) if current_record else None,
                "secret_word_2": decrypt_secret(current_record.freekassa_secret_word_2_encrypted) if current_record else None,
                "sbp_method_id": (
                    current_record.freekassa_sbp_method_id
                    if current_record and current_record.freekassa_sbp_method_id is not None
                    else self.classic_sbp_method_id
                ),
                "require_source_ip_check": self.settings.freekassa_require_source_ip_check,
                "allowed_ips": self.settings.parsed_freekassa_allowed_ips,
            }
        finally:
            if local_db is not None:
                local_db.close()

    def build_public_config(self, public_app_url: str, *, record=None) -> FreeKassaConfigRead:
        runtime = self._load_runtime_config(record=record)
        sbp_method_id = int(runtime["sbp_method_id"])
        base_url = self._resolve_public_url(public_app_url, runtime=runtime)
        endpoints = FreeKassaEndpointsRead(
            notification=FreeKassaEndpointRead(url=self._build_public_url(base_url, self.notification_path)),
            success=FreeKassaEndpointRead(url=self._build_public_url(base_url, self.success_path)),
            failure=FreeKassaEndpointRead(url=self._build_public_url(base_url, self.failure_path)),
        )
        selected_method_label = self.describe_payment_method(sbp_method_id)
        notes: list[str] = [
            "FreeKassa открывает собственный hosted checkout. Даже банковские методы внутри него зависят от сценария, который вернет сам провайдер."
        ]
        if sbp_method_id in {self.classic_sbp_method_id, self.api_sbp_method_id}:
            notes.append("Методы 42 и 44 могут вести в FKwallet-flow, если так настроен checkout FreeKassa для вашего магазина.")
            if sbp_method_id == self.api_sbp_method_id:
                notes.append("Метод 44 работает через API-сценарий FreeKassa и требует отдельной проверки по магазину.")
        elif sbp_method_id in {12, 13, 36}:
            notes.append("Для снижения зависимости от FKwallet можно протестировать МИР, Онлайн банк или Card RUB API. Публичная документация FreeKassa описывает их только по названиям, поэтому реальный UX нужно проверять на вашем магазине.")
        return FreeKassaConfigRead(
            shop_id=runtime["shop_id"],
            has_secret_word=bool(runtime["secret_word"]),
            has_api_key=bool(runtime["api_key"]),
            has_secret_word_2=bool(runtime["secret_word_2"]),
            sbp_method_id=sbp_method_id,
            selected_method_label=selected_method_label,
            require_source_ip_check=bool(runtime["require_source_ip_check"]),
            allowed_ips=list(runtime["allowed_ips"]),
            endpoints=endpoints,
            notes=notes,
        )

    def build_payment_redirect_url(self, redirect_token: str, public_app_url: str | None = None) -> str:
        if public_app_url is None:
            from app.services.system_settings import load_effective_system_settings

            effective_settings = load_effective_system_settings()
            public_app_url = effective_settings.freekassa_public_url or effective_settings.public_app_url
        return self._build_public_url(public_app_url.strip().rstrip("/"), f"{self.payment_redirect_path}/{redirect_token}")

    def _resolve_public_url(self, fallback_public_app_url: str, *, runtime: Mapping[str, object] | None = None) -> str:
        active_runtime = runtime or self._load_runtime_config()
        public_url = active_runtime.get("public_url") or fallback_public_app_url
        return str(public_url).strip().rstrip("/")

    def describe_payment_method(self, value: str | int | None) -> str:
        if value is None:
            return "Онлайн-оплата"
        if isinstance(value, str) and value.lower() == "sbp":
            return self.describe_payment_method(self._resolve_checkout_method_id(value))
        try:
            method_id = int(value)
        except (TypeError, ValueError):
            text_value = str(value).strip()
            return text_value.upper() if text_value else "Онлайн-оплата"
        return self.payment_method_labels.get(method_id, f"FreeKassa #{method_id}")

    def _resolve_checkout_method_id(self, value: str | int) -> int:
        runtime = self._load_runtime_config()
        if isinstance(value, int):
            return value
        if value == "sbp":
            configured_method_id = runtime["sbp_method_id"]
            if configured_method_id is None:
                return self.classic_sbp_method_id
            return int(configured_method_id)
        try:
            return int(value)
        except ValueError as exc:
            raise ServiceError("Неизвестный метод оплаты FreeKassa", 400) from exc

    def _resolve_payment_method_ids(self, value: str | int) -> list[int]:
        runtime = self._load_runtime_config()
        if isinstance(value, int):
            return [value]
        if value == "sbp":
            configured_method_id = runtime["sbp_method_id"]
            if configured_method_id is None:
                return [self.classic_sbp_method_id]
            # Keep symbolic SBP pinned to the configured method and avoid silent
            # fallback into a different provider flow.
            return [int(configured_method_id)]
        try:
            return [int(value)]
        except ValueError as exc:
            raise ServiceError("Неизвестный метод оплаты FreeKassa", 400) from exc

    @staticmethod
    def _extract_api_error(payload: Mapping[str, object], default_message: str) -> str:
        for key in ("error", "msg", "message", "description"):
            value = payload.get(key)
            if value:
                return str(value)
        return default_message

    @staticmethod
    def _is_retryable_payment_method_error(status_code: int, message: str) -> bool:
        normalized = message.lower()
        return status_code in {400, 409, 422, 502} and any(
            fragment in normalized
            for fragment in ("валют", "currency", "недоступ", "метод", "method", "способ", "payment")
        )

    def _sign_api_payload(self, payload: Mapping[str, object]) -> str:
        runtime = self._load_runtime_config()
        api_key = runtime["api_key"]
        if not api_key:
            raise ServiceError("Не настроен API ключ FreeKassa", 503)
        ordered_items = sorted((key, str(value)) for key, value in payload.items())
        raw = "|".join(value for _, value in ordered_items)
        return hmac.new(str(api_key).encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()

    def _post_api(self, path: str, payload: Mapping[str, object]) -> tuple[int, dict]:
        request_payload = dict(payload)
        request_payload["signature"] = self._sign_api_payload(request_payload)

        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(f"{self.api_base_url}/{path.lstrip('/')}", json=request_payload)
        except httpx.HTTPError as exc:
            raise ServiceError(f"Не удалось выполнить запрос к FreeKassa: {exc}", 502) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise ServiceError("FreeKassa вернула некорректный JSON", 502) from exc

        if not isinstance(data, dict):
            raise ServiceError("FreeKassa вернула неожиданный ответ", 502)
        return response.status_code, data

    def build_checkout_url(
        self,
        *,
        merchant_order_id: str,
        amount_kopecks: int,
        payment_method_id: str | int,
        payer_email: str | None = None,
    ) -> str:
        runtime = self._load_runtime_config()
        shop_id = runtime["shop_id"]
        secret_word = runtime["secret_word"]
        if shop_id is None:
            raise ServiceError("Не настроен Shop ID FreeKassa", 503)
        if not secret_word:
            raise ServiceError("Не настроен Secret Word FreeKassa", 503)

        amount = f"{amount_kopecks / 100:.2f}"
        currency = "RUB"
        signature = hashlib.md5(
            f"{shop_id}:{amount}:{secret_word}:{currency}:{merchant_order_id}".encode("utf-8")
        ).hexdigest()
        payload: dict[str, object] = {
            "m": shop_id,
            "oa": amount,
            "o": merchant_order_id,
            "currency": currency,
            "i": self._resolve_checkout_method_id(payment_method_id),
            "s": signature,
            "lang": "ru",
        }
        if payer_email:
            payload["em"] = payer_email
        return f"{self.checkout_base_url}?{urlencode(payload)}"

    def create_payment(
        self,
        *,
        merchant_order_id: str,
        amount_kopecks: int,
        payment_method_id: str | int,
        payer_email: str,
        payer_ip: str | None,
    ) -> dict:
        runtime = self._load_runtime_config()
        if runtime["shop_id"] is None:
            raise ServiceError("Не настроен Shop ID FreeKassa", 503)
        if not payer_ip:
            raise ServiceError("Не удалось определить IP плательщика для FreeKassa", 400)

        amount = f"{amount_kopecks / 100:.2f}"
        candidate_method_ids = self._resolve_payment_method_ids(payment_method_id)
        for index, method_id in enumerate(candidate_method_ids):
            payload: dict[str, object] = {
                "shopId": runtime["shop_id"],
                "nonce": time.time_ns(),
                "paymentId": merchant_order_id,
                "i": method_id,
                "email": payer_email,
                "ip": payer_ip,
                "amount": amount,
                "currency": "RUB",
            }
            status_code, data = self._post_api("orders/create", payload)
            if status_code < 400 and data.get("type") == "success":
                return {**data, "selectedMethodId": method_id}

            message = self._extract_api_error(
                data,
                "FreeKassa не создала заказ",
            )
            effective_status = status_code if status_code >= 400 else 502
            if index + 1 < len(candidate_method_ids) and self._is_retryable_payment_method_error(effective_status, message):
                continue
            raise ServiceError(message, effective_status)

        raise ServiceError("СБП сейчас недоступна для оплаты. Попробуйте позже.", 409)

    def verify_notification(
        self,
        payload: Mapping[str, str],
        *,
        source_ip: str | None = None,
    ) -> FreeKassaNotificationRead:
        runtime = self._load_runtime_config()
        secret_word_2 = runtime["secret_word_2"]
        if not secret_word_2:
            raise ServiceError("Не настроен Secret Word 2 FreeKassa", 503)

        normalized = self.normalize_payload(payload)
        missing = [
            field
            for field in ("MERCHANT_ID", "AMOUNT", "intid", "MERCHANT_ORDER_ID", "SIGN")
            if not normalized.get(field)
        ]
        if missing:
            raise ServiceError(f"Отсутствуют обязательные поля FreeKassa: {', '.join(missing)}", 400)

        if runtime["shop_id"] is not None:
            expected_shop_id = str(runtime["shop_id"])
            if normalized["MERCHANT_ID"] != expected_shop_id:
                raise ServiceError("Неожиданный MERCHANT_ID", 400)

        if bool(runtime["require_source_ip_check"]):
            if not source_ip:
                raise ServiceError("Не удалось определить IP источника", 403)
            if source_ip not in list(runtime["allowed_ips"]):
                raise ServiceError("Неожиданный IP источника", 403)

        expected_sign = hashlib.md5(
            (
                f"{normalized['MERCHANT_ID']}:"
                f"{normalized['AMOUNT']}:"
                f"{secret_word_2}:"
                f"{normalized['MERCHANT_ORDER_ID']}"
            ).encode("utf-8")
        ).hexdigest()
        actual_sign = normalized["SIGN"].lower()
        if not secure_compare(expected_sign.lower(), actual_sign):
            raise ServiceError("Некорректная подпись", 400)

        return FreeKassaNotificationRead(
            merchant_id=normalized["MERCHANT_ID"],
            amount=normalized["AMOUNT"],
            intid=normalized["intid"],
            merchant_order_id=normalized["MERCHANT_ORDER_ID"],
            payer_email=normalized.get("P_EMAIL"),
            payer_phone=normalized.get("P_PHONE"),
            currency_id=normalized.get("CUR_ID"),
            payer_account=normalized.get("payer_account"),
            commission=normalized.get("commission"),
            source_ip=source_ip,
            custom_fields={key: value for key, value in normalized.items() if key.startswith("us_")},
        )

    @staticmethod
    def normalize_payload(payload: Mapping[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in payload.items():
            normalized[str(key)] = str(value).strip()
        return normalized

    @staticmethod
    def resolve_source_ip(headers: Mapping[str, str], client_host: str | None) -> str | None:
        for header_name in ("cf-connecting-ip", "x-real-ip", "x-forwarded-for"):
            raw_value = headers.get(header_name)
            if raw_value:
                return raw_value.split(",")[0].strip()
        return client_host

    def render_payment_page(
        self,
        *,
        brand_name: str,
        order_id: str,
        amount_rub: str,
        payment_method_label: str,
        payment_url: str | None,
        bot_name: str | None = None,
        plan_name: str | None = None,
        is_paid: bool = False,
    ) -> str:
        safe_brand = escape(brand_name)
        safe_order_id = escape(order_id)
        safe_amount = escape(amount_rub)
        safe_method = escape(payment_method_label)
        safe_bot = escape(bot_name) if bot_name else "Telegram-бот"
        safe_plan = escape(plan_name) if plan_name else "Пополнение баланса"
        safe_payment_url = escape(payment_url, quote=True) if payment_url else None
        status_title = "Платеж уже зачислен" if is_paid else "Подтвердите оплату"
        status_message = (
            "Этот платеж уже был успешно обработан. Можно вернуться в бот и проверить баланс."
            if is_paid
            else "Вы открыли персональную платежную ссылку. Нажмите кнопку ниже - откроется страница оплаты по СБП."
        )
        primary_action = (
            f'<a class="primary" href="{safe_payment_url}" rel="noreferrer noopener">Оплатить по СБП</a>'
            if safe_payment_url
            else ""
        )
        auto_redirect = (
            f'<meta http-equiv="refresh" content="2;url={safe_payment_url}">'
            if safe_payment_url
            else ""
        )
        auto_redirect_note = (
            "Если страница оплаты не открылась автоматически, используйте кнопку выше."
            if safe_payment_url
            else "Платежная ссылка уже не требуется."
        )
        return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {auto_redirect}
    <title>{safe_brand} - оплата</title>
    <style>
      body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; background: radial-gradient(circle at top left, rgba(15,118,110,.14), transparent 34%), linear-gradient(180deg, #f5f8fc 0%, #dce8f7 100%); font-family: Manrope, system-ui, sans-serif; color: #0f172a; }}
      main {{ width: min(760px, 100%); padding: 34px; border-radius: 32px; border: 1px solid rgba(148,163,184,.25); background: rgba(255,255,255,.95); box-shadow: 0 24px 70px rgba(15,23,42,.14); }}
      .eyebrow {{ display: inline-block; padding: 10px 14px; border-radius: 999px; background: rgba(15,118,110,.1); color: #0f766e; font-size: 12px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }}
      h1 {{ margin: 18px 0 12px; font-size: clamp(2.5rem, 6vw, 4.2rem); line-height: .94; letter-spacing: -.07em; }}
      p {{ margin: 0; color: #526076; line-height: 1.7; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-top: 24px; }}
      .tile {{ padding: 16px 18px; border-radius: 22px; background: #f8fafc; border: 1px solid rgba(203,213,225,.8); }}
      .tile span {{ display: block; color: #64748b; font-size: .82rem; margin-bottom: 8px; }}
      .tile strong {{ display: block; font-size: 1rem; line-height: 1.45; word-break: break-word; }}
      .actions {{ margin-top: 24px; }}
      .primary {{ display: inline-flex; align-items: center; justify-content: center; min-height: 56px; padding: 0 24px; border-radius: 18px; background: linear-gradient(135deg, #0f766e, #0b5ed7); color: #fff; text-decoration: none; font-weight: 700; }}
      .note {{ margin-top: 18px; padding: 16px 18px; border-radius: 20px; background: linear-gradient(135deg, rgba(15,118,110,.08), rgba(11,94,215,.08)); }}
    </style>
  </head>
  <body>
    <main>
      <div class="eyebrow">Secure payment</div>
      <h1>{escape(status_title)}</h1>
      <p>{escape(status_message)}</p>
      <div class="grid">
        <section class="tile"><span>Бренд</span><strong>{safe_brand}</strong></section>
        <section class="tile"><span>Сумма</span><strong>{safe_amount} RUB</strong></section>
        <section class="tile"><span>Метод</span><strong>{safe_method}</strong></section>
        <section class="tile"><span>Заказ</span><strong>{safe_order_id}</strong></section>
        <section class="tile"><span>Источник</span><strong>{safe_bot}</strong></section>
        <section class="tile"><span>Назначение</span><strong>{safe_plan}</strong></section>
      </div>
      <div class="actions">{primary_action}</div>
      <div class="note">{escape(auto_redirect_note)}</div>
    </main>
  </body>
</html>"""

    def render_return_page(self, *, outcome: str, payload: Mapping[str, str]) -> str:
        normalized = self.normalize_payload(payload)
        order_id = (
            normalized.get("MERCHANT_ORDER_ID")
            or normalized.get("paymentId")
            or normalized.get("o")
            or "not provided"
        )
        status_title = "Оплата завершена" if outcome == "success" else "Оплата не завершена"
        status_message = (
            "Пользователь вернулся из FreeKassa. Финальное подтверждение оплаты приходит отдельным серверным уведомлением."
            if outcome == "success"
            else "Платеж был отменен или платежная система вернула ошибку."
        )
        escaped_title = escape(status_title)
        escaped_message = escape(status_message)
        escaped_order_id = escape(order_id)
        return self._render_html_page(
            title=escaped_title,
            message=escaped_message,
            order_id=escaped_order_id,
        )

    def render_error_page(self, *, title: str, message: str, order_id: str | None = None) -> str:
        return self._render_html_page(
            title=escape(title),
            message=escape(message),
            order_id=escape(order_id) if order_id else None,
        )

    def _render_html_page(self, *, title: str, message: str, order_id: str | None = None) -> str:
        order_markup = f"<strong>Заказ: {order_id}</strong>" if order_id else ""
        return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: linear-gradient(180deg, #f8fbfd 0%, #eef4f8 52%, #dbe7f3 100%);
        font-family: Manrope, system-ui, sans-serif;
        color: #0f172a;
      }}
      main {{
        width: min(560px, calc(100vw - 32px));
        border: 1px solid rgba(226, 232, 240, 0.92);
        border-radius: 28px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
        padding: 32px;
      }}
      h1 {{
        margin: 0 0 12px;
        font-size: clamp(2rem, 5vw, 2.6rem);
        letter-spacing: -0.06em;
      }}
      p {{
        margin: 0;
        color: #5f6f86;
        line-height: 1.6;
      }}
      strong {{
        display: block;
        margin-top: 20px;
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>{title}</h1>
      <p>{message}</p>
      {order_markup}
    </main>
  </body>
</html>"""

    def _build_public_url(self, base_url: str, route_path: str) -> str:
        api_prefix = self.settings.api_v1_prefix.rstrip("/")
        return f"{base_url}{api_prefix}{self.router_prefix}{route_path}"
