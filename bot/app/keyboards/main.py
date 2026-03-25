from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Получить тест 24 часа", callback_data="trial")
    builder.button(text="Мой статус", callback_data="status")
    builder.button(text="Мой конфиг", callback_data="config")
    builder.button(text="Помощь", callback_data="help")
    builder.adjust(1)
    return builder.as_markup()


def config_bundle_keyboard(bundle_kind: str, *, showing_qr: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Показать конфиг" if showing_qr else "Вернуть QR",
        callback_data=f"bundle:{bundle_kind}:{'text' if showing_qr else 'qr'}",
    )
    builder.button(text="Главное меню", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()
