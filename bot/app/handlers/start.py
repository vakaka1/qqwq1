from __future__ import annotations

import io
from contextlib import suppress
from datetime import datetime

import qrcode

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message, User

from app.keyboards.main import config_bundle_keyboard, main_menu_keyboard
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
        "4. Если нужен текущий доступ, откройте «Мой конфиг»."
    )


def _build_status_text(payload: dict) -> str:
    return (
        "Ваш статус\n\n"
        f"Пользователь: {_format_status(payload['status'])}\n"
        f"Тест использован: {'да' if payload['trial_used'] else 'нет'}\n"
        f"Активный доступ: {_format_status(payload['active_access_status'])}\n"
        f"Сервер: {payload['server_name'] or '—'}\n"
        f"Истекает: {_format_datetime(payload['active_access_expires_at'])}"
    )


async def _set_bot_commands(message: Message) -> None:
    await message.bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="status", description="Мой статус"),
        BotCommand(command="trial", description="Попробовать бесплатно"),
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
            await message.answer(f"Backend сейчас недоступен: {exc}")
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
            await message.answer(f"Не удалось получить статус: {exc}")
            return

        await _send_text(message, _build_status_text(payload), reply_markup=main_menu_keyboard())

    @router.message(Command("trial"))
    async def trial_cmd(message: Message) -> None:
        try:
            payload = await client.request_trial({"bot_code": bot_config.code, **_user_payload(message.from_user)})
        except RuntimeError as exc:
            await message.answer(f"Не удалось выдать тест: {exc}")
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
            await message.answer(f"Не удалось получить конфиг: {exc}")
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
            await callback.message.answer(f"Не удалось выдать тест: {exc}")
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
            await callback.message.answer(f"Не удалось получить статус: {exc}")
            await callback.answer()
            return

        await _replace_message_text(
            callback.message,
            _build_status_text(payload),
            reply_markup=main_menu_keyboard(),
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
            await callback.message.answer(f"Не удалось получить конфиг: {exc}")
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
            await callback.message.answer(f"Не удалось получить конфиг: {exc}")
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

    return router
