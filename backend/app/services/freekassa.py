from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from html import escape

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
    router_prefix = "/freekassa"
    notification_path = "/notify"
    success_path = "/success"
    failure_path = "/fail"
    payment_redirect_path = "/pay"
    api_base_url = "https://api.fk.life/v1"

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
                "api_key": decrypt_secret(current_record.freekassa_api_key_encrypted) if current_record else None,
                "secret_word_2": decrypt_secret(current_record.freekassa_secret_word_2_encrypted) if current_record else None,
                "sbp_method_id": (
                    current_record.freekassa_sbp_method_id
                    if current_record and current_record.freekassa_sbp_method_id is not None
                    else 44
                ),
                "require_source_ip_check": self.settings.freekassa_require_source_ip_check,
                "allowed_ips": self.settings.parsed_freekassa_allowed_ips,
            }
        finally:
            if local_db is not None:
                local_db.close()

    def build_public_config(self, public_app_url: str, *, record=None) -> FreeKassaConfigRead:
        runtime = self._load_runtime_config(record=record)
        base_url = public_app_url.strip().rstrip("/")
        endpoints = FreeKassaEndpointsRead(
            notification=FreeKassaEndpointRead(url=self._build_public_url(base_url, self.notification_path)),
            success=FreeKassaEndpointRead(url=self._build_public_url(base_url, self.success_path)),
            failure=FreeKassaEndpointRead(url=self._build_public_url(base_url, self.failure_path)),
        )
        return FreeKassaConfigRead(
            shop_id=runtime["shop_id"],
            has_api_key=bool(runtime["api_key"]),
            has_secret_word_2=bool(runtime["secret_word_2"]),
            sbp_method_id=int(runtime["sbp_method_id"]),
            require_source_ip_check=bool(runtime["require_source_ip_check"]),
            allowed_ips=list(runtime["allowed_ips"]),
            endpoints=endpoints,
            notes=[],
        )

    def build_payment_redirect_url(self, redirect_token: str, public_app_url: str | None = None) -> str:
        if public_app_url is None:
            from app.services.system_settings import load_effective_system_settings

            public_app_url = load_effective_system_settings().public_app_url
        return self._build_public_url(public_app_url.strip().rstrip("/"), f"{self.payment_redirect_path}/{redirect_token}")

    def _resolve_payment_method_id(self, value: str | int) -> int:
        runtime = self._load_runtime_config()
        if isinstance(value, int):
            return value
        if value == "sbp":
            return int(runtime["sbp_method_id"])
        try:
            return int(value)
        except ValueError as exc:
            raise ServiceError("Неизвестный метод оплаты FreeKassa", 400) from exc

    def _sign_api_payload(self, payload: Mapping[str, object]) -> str:
        runtime = self._load_runtime_config()
        api_key = runtime["api_key"]
        if not api_key:
            raise ServiceError("Не настроен API ключ FreeKassa", 503)
        ordered_items = sorted((key, str(value)) for key, value in payload.items())
        raw = "|".join(value for _, value in ordered_items)
        return hmac.new(str(api_key).encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()

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
        payload: dict[str, object] = {
            "shopId": runtime["shop_id"],
            "nonce": time.time_ns(),
            "paymentId": merchant_order_id,
            "i": self._resolve_payment_method_id(payment_method_id),
            "email": payer_email,
            "ip": payer_ip,
            "amount": amount,
            "currency": "RUB",
        }
        payload["signature"] = self._sign_api_payload(payload)

        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(f"{self.api_base_url}/orders/create", json=payload)
        except httpx.HTTPError as exc:
            raise ServiceError(f"Не удалось создать заказ в FreeKassa: {exc}", 502) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise ServiceError("FreeKassa вернула некорректный JSON", 502) from exc

        if response.status_code >= 400:
            message = data.get("error") or data.get("msg") or data.get("message") or "FreeKassa отклонила запрос"
            raise ServiceError(str(message), response.status_code)
        if data.get("type") != "success":
            message = data.get("error") or data.get("msg") or data.get("message") or "FreeKassa не создала заказ"
            raise ServiceError(str(message), 502)
        return data

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
