from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🟢 Открыть смену")],
            [KeyboardButton(text="☕ Взять перерыв"), KeyboardButton(text="✅ Закончить перерыв")],
        ],
        resize_keyboard=True,
    )


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Список сотрудников")],
        ],
        resize_keyboard=True,
    )


def approve_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{telegram_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{telegram_id}"),
        ]]
    )
