from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🟢 Открыть смену")],
            [KeyboardButton(text="☕ Взять перерыв"), KeyboardButton(text="✅ Закончить перерыв")],
            [KeyboardButton(text="🔴 Закрыть смену")],
        ],
        resize_keyboard=True,
    )


def superadmin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🟢 Открыть смену")],
            [KeyboardButton(text="☕ Взять перерыв"), KeyboardButton(text="✅ Закончить перерыв")],
            [KeyboardButton(text="🔴 Закрыть смену")],
            [KeyboardButton(text="👥 Список сотрудников"), KeyboardButton(text="📊 Статистика")],
        ],
        resize_keyboard=True,
    )


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Список сотрудников"), KeyboardButton(text="📊 Статистика")],
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


def staff_picker_keyboard(employees: list) -> InlineKeyboardMarkup:
    """Инлайн-кнопки со списком сотрудников для просмотра статистики."""
    buttons = []
    for emp in employees:
        buttons.append([
            InlineKeyboardButton(
                text=emp["full_name"],
                callback_data=f"stat_emp:{emp['telegram_id']}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def stat_type_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    """Выбор типа статистики: смены за неделю или перерывы."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Смены за неделю", callback_data=f"stat_shifts:{telegram_id}")],
            [InlineKeyboardButton(text="☕ Перерывы за день", callback_data=f"stat_breaks_days:{telegram_id}")],
        ]
    )


def day_picker_keyboard(telegram_id: int, days: list) -> InlineKeyboardMarkup:
    """Кнопки с датами для выбора дня перерывов."""
    from datetime import datetime
    buttons = []
    for day in days:
        try:
            label = datetime.strptime(day, "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            label = day
        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"stat_breaks:{telegram_id}:{day}"
            )
        ])
    if not buttons:
        buttons.append([InlineKeyboardButton(text="Нет данных", callback_data="noop")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
