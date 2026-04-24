from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove,
)


# ── Состояния меню ────────────────────────────────────────────────────────────

def menu_default(is_superadmin: bool = False) -> ReplyKeyboardMarkup:
    """Нет открытой смены — только кнопка открыть смену."""
    rows = [[KeyboardButton(text="🟢 Открыть смену")]]
    if is_superadmin:
        rows.append([KeyboardButton(text="👥 Список сотрудников"), KeyboardButton(text="📊 Статистика")])
        rows.append([KeyboardButton(text="👁 Активные смены")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def menu_shift_open(is_superadmin: bool = False) -> ReplyKeyboardMarkup:
    """Смена открыта, перерыва нет."""
    rows = [
        [KeyboardButton(text="☕ Взять перерыв")],
        [KeyboardButton(text="🔴 Закрыть смену")],
    ]
    if is_superadmin:
        rows.append([KeyboardButton(text="👥 Список сотрудников"), KeyboardButton(text="📊 Статистика")])
        rows.append([KeyboardButton(text="👁 Активные смены")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def menu_on_break(is_superadmin: bool = False) -> ReplyKeyboardMarkup:
    """Перерыв активен — только завершить перерыв."""
    rows = [[KeyboardButton(text="✅ Закончить перерыв")]]
    if is_superadmin:
        rows.append([KeyboardButton(text="👥 Список сотрудников"), KeyboardButton(text="📊 Статистика")])
        rows.append([KeyboardButton(text="👁 Активные смены")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def menu_admin() -> ReplyKeyboardMarkup:
    """Для обычных админов (управляющих) без функций сотрудника."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Список сотрудников")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👁 Активные смены")]
        ],
        resize_keyboard=True,
    )


# ── Меню ожидания фото с кнопкой отмены ──────────────────────────────────────

def menu_cancel() -> ReplyKeyboardMarkup:
    """Показывается когда бот ждёт фото — единственная опция это отмена."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


# ── Инлайн-клавиатуры ─────────────────────────────────────────────────────────

def approve_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{telegram_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{telegram_id}"),
        ]]
    )


def staff_picker_keyboard(employees: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=emp["full_name"], callback_data=f"stat_emp:{emp['telegram_id']}")]
        for emp in employees
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def stat_type_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Смены за неделю", callback_data=f"stat_shifts:{telegram_id}")],
            [InlineKeyboardButton(text="☕ Перерывы за день", callback_data=f"stat_breaks_days:{telegram_id}")],
        ]
    )


def day_picker_keyboard(telegram_id: int, days: list) -> InlineKeyboardMarkup:
    from datetime import datetime
    buttons = []
    for day in days:
        try:
            label = datetime.strptime(day, "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            label = day
        buttons.append([
            InlineKeyboardButton(text=label, callback_data=f"stat_breaks:{telegram_id}:{day}")
        ])
    if not buttons:
        buttons.append([InlineKeyboardButton(text="Нет данных", callback_data="noop")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
