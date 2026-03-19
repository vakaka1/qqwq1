from __future__ import annotations

from datetime import datetime
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message, User

from app.keyboards.main import main_menu_keyboard
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


async def _answer_markdown(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    await message.answer(
        text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=reply_markup,
    )


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


async def _send_config_bundle(
    message: Message,
    *,
    title: str,
    summary: str,
    config_uri: str,
) -> None:
    text = f"{title}\n\n{summary}\n\n*URI*\n`{config_uri}`"
    if len(text) <= 3800:
        await _answer_markdown(message, text)
        return

    await _answer_markdown(
        message,
        f"{title}\n\n{summary}\n\nПолный URI отправлен отдельным файлом.",
    )
    await message.answer_document(
        BufferedInputFile(config_uri.encode("utf-8"), filename="vless-config.txt"),
        caption="Полный VLESS URI",
    )


def _default_welcome_text(bot_config: ManagedBotRuntimeConfig) -> str:
    return (
        f"*{bot_config.name}*\n\n"
        "Выберите действие ниже:\n"
        "• получить тестовый доступ\n"
        "• проверить текущий статус\n"
        "• забрать активный конфиг\n"
        "• открыть подсказку по подключению"
    )


def _default_help_text() -> str:
    return (
        "*Как подключиться*\n\n"
        "1. Нажмите «Получить тест 24 часа».\n"
        "2. Получите готовый VLESS URI.\n"
        "3. Импортируйте его в совместимый клиент.\n"
        "4. Если нужен текущий доступ, откройте «Мой конфиг»."
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

        await _answer_markdown(message, _default_welcome_text(bot_config), reply_markup=main_menu_keyboard())

    @router.message(Command("status"))
    async def status_cmd(message: Message) -> None:
        user = message.from_user
        if not user: return
        try:
            payload = await client.get_user(user.id, bot_config.code)
        except RuntimeError as exc:
            await message.answer(f"Не удалось получить статус: {exc}")
            return

        await _answer_markdown(
            message,
            (
                "*Ваш статус*\n\n"
                f"*Пользователь:* {_format_status(payload['status'])}\n"
                f"*Тест использован:* {'да' if payload['trial_used'] else 'нет'}\n"
                f"*Активный доступ:* {_format_status(payload['active_access_status'])}\n"
                f"*Сервер:* {payload['server_name'] or '—'}\n"
                f"*Истекает:* {_format_datetime(payload['active_access_expires_at'])}"
            ),
        )

    @router.message(Command("trial"))
    async def trial_cmd(message: Message) -> None:
        try:
            payload = await client.request_trial({"bot_code": bot_config.code, **_user_payload(message.from_user)})
        except RuntimeError as exc:
            await message.answer(f"Не удалось выдать тест: {exc}")
            return

        await _send_config_bundle(
            message,
            title="*Тестовый доступ выдан*",
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

        await _send_config_bundle(
            message,
            title="*Ваш активный конфиг*",
            summary=payload["config_text"],
            config_uri=payload["config_uri"],
        )

    @router.message(Command("help"))
    async def help_cmd(message: Message) -> None:
        if bot_config.help_text:
            await _answer_custom_text(message, bot_config.help_text)
        else:
            await _answer_markdown(message, _default_help_text())

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

        await _send_config_bundle(
            callback.message,
            title="*Тестовый доступ выдан*",
            summary=payload["config_text"],
            config_uri=payload["config_uri"],
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

        await _answer_markdown(
            callback.message,
            (
                "*Ваш статус*\n\n"
                f"*Пользователь:* {_format_status(payload['status'])}\n"
                f"*Тест использован:* {'да' if payload['trial_used'] else 'нет'}\n"
                f"*Активный доступ:* {_format_status(payload['active_access_status'])}\n"
                f"*Сервер:* {payload['server_name'] or '—'}\n"
                f"*Истекает:* {_format_datetime(payload['active_access_expires_at'])}"
            ),
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

        await _send_config_bundle(
            callback.message,
            title="*Ваш активный конфиг*",
            summary=payload["config_text"],
            config_uri=payload["config_uri"],
        )
        await callback.answer()

    @router.callback_query(F.data == "help")
    async def help_message(callback: CallbackQuery) -> None:
        if callback.message:
            if bot_config.help_text:
                await _answer_custom_text(callback.message, bot_config.help_text)
            else:
                await _answer_markdown(callback.message, _default_help_text())
        await callback.answer()

    return router
