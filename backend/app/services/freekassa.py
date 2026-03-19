from __future__ import annotations

import hashlib
from collections.abc import Mapping
from html import escape

from app.config.settings import get_settings
from app.core.security import secure_compare
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

    def __init__(self) -> None:
        self.settings = get_settings()

    def build_public_config(self, public_app_url: str) -> FreeKassaConfigRead:
        base_url = public_app_url.strip().rstrip("/")
        endpoints = FreeKassaEndpointsRead(
            notification=FreeKassaEndpointRead(url=self._build_public_url(base_url, self.notification_path)),
            success=FreeKassaEndpointRead(url=self._build_public_url(base_url, self.success_path)),
            failure=FreeKassaEndpointRead(url=self._build_public_url(base_url, self.failure_path)),
        )
        notes = [
            "В кабинете FreeKassa для всех трех URL установите метод POST.",
            "Подпись формы оплаты считается как md5(shopId:amount:secret word:currency:orderId).",
            "Подпись уведомления считается как md5(MERCHANT_ID:AMOUNT:secret word 2:MERCHANT_ORDER_ID).",
            "Success URL нужен только для возврата пользователя. Подтверждать оплату нужно по notification URL.",
            "Если в кабинете включено подтверждение платежа, notification URL должен отвечать ровно YES.",
        ]
        if self.settings.parsed_freekassa_allowed_ips:
            notes.append(
                "FreeKassa рекомендует проверять IP источника уведомлений: "
                + ", ".join(self.settings.parsed_freekassa_allowed_ips)
                + "."
            )
        if not self.settings.freekassa_secret_word_2:
            notes.append("FREEKASSA_SECRET_WORD_2 пока не задан, поэтому верификация notification URL не будет работать.")
        return FreeKassaConfigRead(
            shop_id=self.settings.freekassa_shop_id,
            has_secret_word=bool(self.settings.freekassa_secret_word),
            has_secret_word_2=bool(self.settings.freekassa_secret_word_2),
            require_source_ip_check=self.settings.freekassa_require_source_ip_check,
            allowed_ips=self.settings.parsed_freekassa_allowed_ips,
            endpoints=endpoints,
            notes=notes,
        )

    def verify_notification(
        self,
        payload: Mapping[str, str],
        *,
        source_ip: str | None = None,
    ) -> FreeKassaNotificationRead:
        secret_word_2 = self.settings.freekassa_secret_word_2
        if not secret_word_2:
            raise ServiceError("FREEKASSA_SECRET_WORD_2 не настроен", 503)

        normalized = self.normalize_payload(payload)
        missing = [
            field
            for field in ("MERCHANT_ID", "AMOUNT", "intid", "MERCHANT_ORDER_ID", "SIGN")
            if not normalized.get(field)
        ]
        if missing:
            raise ServiceError(f"Отсутствуют обязательные поля FreeKassa: {', '.join(missing)}", 400)

        if self.settings.freekassa_shop_id is not None:
            expected_shop_id = str(self.settings.freekassa_shop_id)
            if normalized["MERCHANT_ID"] != expected_shop_id:
                raise ServiceError("Неожиданный MERCHANT_ID", 400)

        if self.settings.freekassa_require_source_ip_check:
            if not source_ip:
                raise ServiceError("Не удалось определить IP источника", 403)
            if source_ip not in self.settings.parsed_freekassa_allowed_ips:
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
        return f"""<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escaped_title}</title>
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
      <h1>{escaped_title}</h1>
      <p>{escaped_message}</p>
      <strong>Заказ: {escaped_order_id}</strong>
    </main>
  </body>
</html>"""

    def _build_public_url(self, base_url: str, route_path: str) -> str:
        api_prefix = self.settings.api_v1_prefix.rstrip("/")
        return f"{base_url}{api_prefix}{self.router_prefix}{route_path}"
