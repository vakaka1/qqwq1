from __future__ import annotations

import io
from contextlib import suppress
from datetime import datetime

import qrcode

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message, User

from app.keyboards.main import config_bundle_keyboard, main_menu_keyboard, payment_keyboard, plans_keyboard
from app.services.backend_client import BackendClient, ManagedBotRuntimeConfig


def _user_payload(user: User) -> dict:
    return {
        "telegram_user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language_code": user.language_code,
    }


def _format_datetime(value: str | None) -> str:
    if not value:
        return "—"
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    return parsed.strftime("%d.%m.%Y %H:%M")


def _format_status(value: str | None) -> str:
    labels = {
        "new": "новый",
        "active": "активен",
        "expired": "истек",
        "disabled": "отключен",
        "deleted": "удален",
    }
    if not value:
        return "—"
    return labels.get(value.lower(), value)


def _is_not_modified_error(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in str(exc).lower()


def _escape_markdown_v2(value: str) -> str:
    escaped = value
    for char in ("\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def _is_internal_error_message(detail: str) -> bool:
    lowered = detail.lower()
    internal_markers = (
        "3x-ui",
        "3x_ui",
        "freekassa",
        "traceback",
        "sqlalchemy",
        "http ",
        "/inbounds",
        "/orders/create",
        "connection refused",
        "timed out",
        "api.fk.life",
    )
    return any(marker in lowered for marker in internal_markers)


def _user_visible_error(detail: str, fallback: str) -> str:
    cleaned = detail.strip()
    if not cleaned:
        return fallback
    if _is_internal_error_message(cleaned):
        return fallback
    return cleaned


async def _send_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    await message.answer(text, disable_web_page_preview=True, reply_markup=reply_markup)


async def _answer_custom_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.answer(
            text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest:
        await message.answer(text, disable_web_page_preview=True, reply_markup=reply_markup)


async def _replace_message_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.edit_text(text, disable_web_page_preview=True, reply_markup=reply_markup)
        return
    except TelegramBadRequest as exc:
        if _is_not_modified_error(exc):
            return

    await message.answer(text, disable_web_page_preview=True, reply_markup=reply_markup)
    with suppress(TelegramBadRequest):
        await message.delete()


async def _replace_message_custom_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.edit_text(
            text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        return
    except TelegramBadRequest as exc:
        if _is_not_modified_error(exc):
            return

    await _answer_custom_text(message, text, reply_markup=reply_markup)
    with suppress(TelegramBadRequest):
        await message.delete()


def _build_config_qr_file(config_uri: str) -> BufferedInputFile:
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(config_uri)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return BufferedInputFile(buffer.getvalue(), filename="vless-config-qr.png")


def _build_config_qr_caption(title: str, summary: str) -> str:
    parts = [title, "", summary.strip() or "Конфиг готов.", "", "Нажмите кнопку ниже, чтобы показать полный URI."]
    caption = "\n".join(parts).strip()
    if len(caption) <= 1024:
        return caption
    return f"{title}\n\nКонфиг готов. Полный URI доступен по кнопке ниже."


def _build_config_text(title: str, summary: str, config_uri: str) -> str:
    parts = [_escape_markdown_v2(title)]
    cleaned_summary = summary.strip()
    if cleaned_summary:
        parts.extend(["", _escape_markdown_v2(cleaned_summary)])
    parts.extend(["", _escape_markdown_v2("Полный VLESS URI:"), f"`{config_uri}`"])
    return "\n".join(parts)


async def _send_or_replace_config_qr(
    message: Message,
    *,
    bundle_kind: str,
    title: str,
    summary: str,
    config_uri: str,
    replace: bool = False,
) -> None:
    reply_markup = config_bundle_keyboard(bundle_kind, showing_qr=True)
    if replace:
        await message.answer_photo(
            photo=_build_config_qr_file(config_uri),
            caption=_build_config_qr_caption(title, summary),
            reply_markup=reply_markup,
        )
        with suppress(TelegramBadRequest):
            await message.delete()
        return

    await message.answer_photo(
        photo=_build_config_qr_file(config_uri),
        caption=_build_config_qr_caption(title, summary),
        reply_markup=reply_markup,
    )


async def _send_or_replace_config_text(
    message: Message,
    *,
    bundle_kind: str,
    title: str,
    summary: str,
    config_uri: str,
    replace: bool = False,
) -> None:
    text = _build_config_text(title, summary, config_uri)
    if len(text) > 4000:
        text = f"{title}\n\nПолный URI слишком длинный для одного сообщения. Используйте QR-код."

    reply_markup = config_bundle_keyboard(bundle_kind, showing_qr=False)
    if replace:
        await message.answer(
            text,
            parse_mode="MarkdownV2",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        with suppress(TelegramBadRequest):
            await message.delete()
        return

    await message.answer(
        text,
        parse_mode="MarkdownV2",
        disable_web_page_preview=True,
        reply_markup=reply_markup,
    )


def _default_welcome_text(bot_config: ManagedBotRuntimeConfig) -> str:
    return (
        f"{bot_config.name}\n\n"
        "Выберите действие ниже:\n"
        "• получить тестовый доступ\n"
        "• пополнить баланс и продлить доступ\n"
        "• проверить текущий статус\n"
        "• забрать активный конфиг\n"
        "• открыть подсказку по подключению"
    )


def _default_help_text() -> str:
    return (
        "Как подключиться\n\n"
        "1. Нажмите «Получить тест 24 часа».\n"
        "2. Получите QR-код или готовый VLESS URI.\n"
        "3. Импортируйте его в совместимый клиент.\n"
        "4. Для продления сначала пополните баланс.\n"
        "5. Затем выберите тариф в разделе продления."
    )


def _build_status_text(payload: dict) -> str:
    return (
        "Ваш статус\n\n"
        f"Пользователь: {_format_status(payload['status'])}\n"
        f"Тест доступен: {'да' if payload['can_use_trial'] else 'нет'}\n"
        f"Тест использован: {'да' if payload['trial_used'] else 'нет'}\n"
        f"Баланс: {payload['balance_rub']} RUB\n"
        f"Активный доступ: {_format_status(payload['active_access_status'])}\n"
        f"Сервер: {payload['server_name'] or '—'}\n"
        f"Истекает: {_format_datetime(payload['active_access_expires_at'])}"
    )


def _build_balance_text(payload: dict) -> str:
    wallet = payload["wallet"]
    return (
        "Баланс\n\n"
        f"Доступно: {wallet['balance_rub']} RUB\n"
        f"Тест доступен: {'да' if not wallet['trial_used'] else 'нет'}\n"
        f"Тест истекает: {_format_datetime(wallet['trial_ends_at'])}\n\n"
        "После оплаты баланс обновится отдельным сообщением."
    )


def _build_plans_text(payload: dict) -> str:
    plans = payload.get("plans", [])
    if not plans:
        return "Тарифы пока не настроены."
    lines = ["Тарифы продления", ""]
    for plan in plans:
        description = f" · {plan['description']}" if plan.get("description") else ""
        lines.append(f"• {plan['name']} — {plan['duration_label']} — {plan['price_rub']} RUB{description}")
    lines.extend(["", "Выберите тариф кнопкой ниже. Если баланса не хватает, бот предложит оплату."])
    return "\n".join(lines)


def _find_plan(payload: dict, plan_id: str) -> dict | None:
    for plan in payload.get("plans", []):
        if plan["id"] == plan_id:
            return plan
    return None


async def _set_bot_commands(message: Message) -> None:
    await message.bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="status", description="Мой статус"),
        BotCommand(command="trial", description="Попробовать бесплатно"),
        BotCommand(command="balance", description="Баланс и оплата"),
        BotCommand(command="plans", description="Тарифы продления"),
        BotCommand(command="config", description="Получить конфиг"),
        BotCommand(command="help", description="Помощь"),
    ])


def build_router(client: BackendClient, bot_config: ManagedBotRuntimeConfig) -> Router:
    router = Router()

    @router.message(CommandStart())
    @router.message(Command("menu"))
    async def start(message: Message) -> None:
        await _set_bot_commands(message)
        try:
            await client.start({"bot_code": bot_config.code, **_user_payload(message.from_user)})
        except RuntimeError as exc:
            await message.answer(_user_visible_error(str(exc), "Сервис временно недоступен. Попробуйте позже."))
            return

        if bot_config.welcome_text:
            await _answer_custom_text(message, bot_config.welcome_text, reply_markup=main_menu_keyboard())
            return

        await _send_text(message, _default_welcome_text(bot_config), reply_markup=main_menu_keyboard())

    @router.message(Command("status"))
    async def status_cmd(message: Message) -> None:
        user = message.from_user
        if not user: return
        try:
            payload = await client.get_user(user.id, bot_config.code)
        except RuntimeError as exc:
            await message.answer(_user_visible_error(str(exc), "Не удалось получить статус. Попробуйте позже."))
            return

        await _send_text(message, _build_status_text(payload), reply_markup=main_menu_keyboard())

    @router.message(Command("balance"))
    async def balance_cmd(message: Message) -> None:
        user = message.from_user
        if not user:
            return
        try:
            payload = await client.get_billing(user.id, bot_config.code)
        except RuntimeError as exc:
            await message.answer(_user_visible_error(str(exc), "Не удалось получить баланс. Попробуйте позже."))
            return

        await _send_text(
            message,
            _build_balance_text(payload),
            reply_markup=plans_keyboard(payload.get("plans", []), mode="topup"),
        )

    @router.message(Command("plans"))
    async def plans_cmd(message: Message) -> None:
        user = message.from_user
        if not user:
            return
        try:
            payload = await client.get_billing(user.id, bot_config.code)
        except RuntimeError as exc:
            await message.answer(_user_visible_error(str(exc), "Не удалось загрузить тарифы. Попробуйте позже."))
            return

        await _send_text(
            message,
            _build_plans_text(payload),
            reply_markup=plans_keyboard(payload.get("plans", []), mode="buy"),
        )

    @router.message(Command("trial"))
    async def trial_cmd(message: Message) -> None:
        try:
            payload = await client.request_trial({"bot_code": bot_config.code, **_user_payload(message.from_user)})
        except RuntimeError as exc:
            await message.answer(_user_visible_error(str(exc), "Не удалось выдать тестовый доступ. Попробуйте позже."))
            return

        await _send_or_replace_config_qr(
            message,
            bundle_kind="trial",
            title="Тестовый доступ выдан",
            summary=payload["config_text"],
            config_uri=payload["config_uri"],
        )

    @router.message(Command("config"))
    async def config_cmd(message: Message) -> None:
        user = message.from_user
        if not user: return
        try:
            payload = await client.get_config(user.id, bot_config.code)
        except RuntimeError as exc:
            await message.answer(_user_visible_error(str(exc), "Не удалось получить конфиг. Попробуйте позже."))
            return

        await _send_or_replace_config_qr(
            message,
            bundle_kind="config",
            title="Ваш активный конфиг",
            summary=payload["config_text"],
            config_uri=payload["config_uri"],
        )

    @router.message(Command("help"))
    async def help_cmd(message: Message) -> None:
        if bot_config.help_text:
            await _answer_custom_text(message, bot_config.help_text, reply_markup=main_menu_keyboard())
        else:
            await _send_text(message, _default_help_text(), reply_markup=main_menu_keyboard())

    @router.callback_query(F.data == "menu")
    async def show_menu(callback: CallbackQuery) -> None:
        if not callback.message:
            await callback.answer()
            return

        if bot_config.welcome_text:
            await _replace_message_custom_text(
                callback.message,
                bot_config.welcome_text,
                reply_markup=main_menu_keyboard(),
            )
        else:
            await _replace_message_text(
                callback.message,
                _default_welcome_text(bot_config),
                reply_markup=main_menu_keyboard(),
            )
        await callback.answer()

    @router.callback_query(F.data == "trial")
    async def request_trial(callback: CallbackQuery) -> None:
        if not callback.message:
            return
        try:
            payload = await client.request_trial({"bot_code": bot_config.code, **_user_payload(callback.from_user)})
        except RuntimeError as exc:
            await callback.message.answer(
                _user_visible_error(str(exc), "Не удалось выдать тестовый доступ. Попробуйте позже.")
            )
            await callback.answer()
            return

        await _send_or_replace_config_qr(
            callback.message,
            bundle_kind="trial",
            title="Тестовый доступ выдан",
            summary=payload["config_text"],
            config_uri=payload["config_uri"],
            replace=True,
        )
        await callback.answer("Тест выдан")

    @router.callback_query(F.data == "status")
    async def status(callback: CallbackQuery) -> None:
        if not callback.message:
            return
        user = callback.from_user
        try:
            payload = await client.get_user(user.id, bot_config.code)
        except RuntimeError as exc:
            await callback.message.answer(
                _user_visible_error(str(exc), "Не удалось получить статус. Попробуйте позже.")
            )
            await callback.answer()
            return

        await _replace_message_text(
            callback.message,
            _build_status_text(payload),
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data == "balance")
    async def balance(callback: CallbackQuery) -> None:
        if not callback.message:
            return
        try:
            payload = await client.get_billing(callback.from_user.id, bot_config.code)
        except RuntimeError as exc:
            await callback.message.answer(
                _user_visible_error(str(exc), "Не удалось получить баланс. Попробуйте позже.")
            )
            await callback.answer()
            return

        await _replace_message_text(
            callback.message,
            _build_balance_text(payload),
            reply_markup=plans_keyboard(payload.get("plans", []), mode="topup"),
        )
        await callback.answer()

    @router.callback_query(F.data == "renew")
    async def renew(callback: CallbackQuery) -> None:
        if not callback.message:
            return
        try:
            payload = await client.get_billing(callback.from_user.id, bot_config.code)
        except RuntimeError as exc:
            await callback.message.answer(
                _user_visible_error(str(exc), "Не удалось загрузить тарифы. Попробуйте позже.")
            )
            await callback.answer()
            return

        await _replace_message_text(
            callback.message,
            _build_plans_text(payload),
            reply_markup=plans_keyboard(payload.get("plans", []), mode="buy"),
        )
        await callback.answer()

    @router.callback_query(F.data == "config")
    async def config(callback: CallbackQuery) -> None:
        if not callback.message:
            return
        user = callback.from_user
        try:
            payload = await client.get_config(user.id, bot_config.code)
        except RuntimeError as exc:
            await callback.message.answer(
                _user_visible_error(str(exc), "Не удалось получить конфиг. Попробуйте позже.")
            )
            await callback.answer()
            return

        await _send_or_replace_config_qr(
            callback.message,
            bundle_kind="config",
            title="Ваш активный конфиг",
            summary=payload["config_text"],
            config_uri=payload["config_uri"],
            replace=True,
        )
        await callback.answer()

    @router.callback_query(F.data == "help")
    async def help_message(callback: CallbackQuery) -> None:
        if callback.message:
            if bot_config.help_text:
                await _replace_message_custom_text(
                    callback.message,
                    bot_config.help_text,
                    reply_markup=main_menu_keyboard(),
                )
            else:
                await _replace_message_text(
                    callback.message,
                    _default_help_text(),
                    reply_markup=main_menu_keyboard(),
                )
        await callback.answer()

    @router.callback_query(F.data.startswith("bundle:"))
    async def toggle_bundle_view(callback: CallbackQuery) -> None:
        if not callback.message or not callback.data:
            await callback.answer()
            return

        _, bundle_kind, view_mode = callback.data.split(":", maxsplit=2)
        try:
            payload = await client.get_config(callback.from_user.id, bot_config.code)
        except RuntimeError as exc:
            await callback.message.answer(
                _user_visible_error(str(exc), "Не удалось получить конфиг. Попробуйте позже.")
            )
            await callback.answer()
            return

        title = "Тестовый доступ выдан" if bundle_kind == "trial" else "Ваш активный конфиг"
        if view_mode == "text":
            await _send_or_replace_config_text(
                callback.message,
                bundle_kind=bundle_kind,
                title=title,
                summary=payload["config_text"],
                config_uri=payload["config_uri"],
                replace=True,
            )
        else:
            await _send_or_replace_config_qr(
                callback.message,
                bundle_kind=bundle_kind,
                title=title,
                summary=payload["config_text"],
                config_uri=payload["config_uri"],
                replace=True,
                )
        await callback.answer()

    @router.callback_query(F.data.startswith("plan:"))
    async def plan_action(callback: CallbackQuery) -> None:
        if not callback.message or not callback.data:
            await callback.answer()
            return

        _, mode, plan_id = callback.data.split(":", maxsplit=2)
        try:
            billing = await client.get_billing(callback.from_user.id, bot_config.code)
        except RuntimeError as exc:
            await callback.message.answer(
                _user_visible_error(str(exc), "Не удалось загрузить тарифы. Попробуйте позже.")
            )
            await callback.answer()
            return

        plan = _find_plan(billing, plan_id)
        if not plan:
            await callback.message.answer("Тариф больше недоступен.")
            await callback.answer()
            return

        if mode == "topup":
            try:
                payment = await client.create_top_up_payment(
                    {
                        "bot_code": bot_config.code,
                        "telegram_user_id": callback.from_user.id,
                        "plan_id": plan_id,
                        "cover_shortfall_for_plan": False,
                    }
                )
            except RuntimeError as exc:
                await callback.message.answer(
                    _user_visible_error(str(exc), "Не удалось открыть оплату. Попробуйте позже.")
                )
                await callback.answer()
                return

            text = (
                "Пополнение баланса\n\n"
                f"Сумма: {payment['amount_rub']} RUB\n"
                "Нажмите кнопку ниже, откроется страница оплаты."
            )
            await _replace_message_text(
                callback.message,
                text,
                reply_markup=payment_keyboard(payment["payment_url"]),
            )
            await callback.answer("Ссылка на оплату готова")
            return

        if billing["wallet"]["balance_kopecks"] < plan["price_kopecks"]:
            try:
                payment = await client.create_top_up_payment(
                    {
                        "bot_code": bot_config.code,
                        "telegram_user_id": callback.from_user.id,
                        "plan_id": plan_id,
                        "cover_shortfall_for_plan": True,
                    }
                )
            except RuntimeError as exc:
                await callback.message.answer(
                    _user_visible_error(str(exc), "Не удалось открыть оплату. Попробуйте позже.")
                )
                await callback.answer()
                return

            text = (
                "Недостаточно средств\n\n"
                f"Тариф: {plan['name']}\n"
                f"Стоимость: {plan['price_rub']} RUB\n"
                f"К доплате: {payment['amount_rub']} RUB\n\n"
                "Нажмите кнопку ниже, чтобы пополнить баланс."
            )
            await _replace_message_text(
                callback.message,
                text,
                reply_markup=payment_keyboard(payment["payment_url"]),
            )
            await callback.answer("Нужно пополнить баланс")
            return

        try:
            purchase = await client.purchase_plan(
                {
                    "bot_code": bot_config.code,
                    "telegram_user_id": callback.from_user.id,
                    "plan_id": plan_id,
                }
            )
        except RuntimeError as exc:
            await callback.message.answer(
                _user_visible_error(str(exc), "Не удалось продлить доступ. Попробуйте позже.")
            )
            await callback.answer()
            return

        summary = (
            f"Списано: {purchase['charged_rub']} RUB\n"
            f"Остаток: {purchase['balance_rub']} RUB\n"
            f"Истекает: {_format_datetime(purchase['expires_at'])}"
        )
        await _send_or_replace_config_qr(
            callback.message,
            bundle_kind="config",
            title="Доступ продлен",
            summary=summary,
            config_uri=purchase["config_uri"],
            replace=True,
        )
        await callback.answer("Доступ продлен")

    return router
