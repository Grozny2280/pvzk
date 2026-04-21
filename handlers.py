from datetime import datetime, timezone, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart

from config import ADMIN_IDS, SUPERADMIN_IDS, PVZ_ADDRESS, GROUP_CHAT_ID
import database as db
from keyboards import (
    main_menu, superadmin_menu, admin_menu, approve_keyboard,
    staff_picker_keyboard, stat_type_keyboard, day_picker_keyboard,
)

router = Router()

ALL_ADMINS = ADMIN_IDS + SUPERADMIN_IDS
MSK = timezone(timedelta(hours=3))


# ── FSM States ────────────────────────────────────────────────────────────────

class Registration(StatesGroup):
    waiting_name = State()
    waiting_wb_id = State()

class ShiftOpen(StatesGroup):
    waiting_photo = State()

class ShiftClose(StatesGroup):
    waiting_photo = State()

class BreakStart(StatesGroup):
    waiting_photo = State()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def notify_admins(bot: Bot, text: str, photo_file_id: str = None):
    """Только в личку админам (регистрации)."""
    for admin_id in ALL_ADMINS:
        try:
            if photo_file_id:
                await bot.send_photo(admin_id, photo=photo_file_id, caption=text, parse_mode="Markdown")
            else:
                await bot.send_message(admin_id, text, parse_mode="Markdown")
        except Exception:
            pass


async def notify_shift(bot: Bot, text: str, photo_file_id: str = None):
    """Смены/перерывы — в личку админам и в групповой чат."""
    for admin_id in ALL_ADMINS:
        try:
            if photo_file_id:
                await bot.send_photo(admin_id, photo=photo_file_id, caption=text, parse_mode="Markdown")
            else:
                await bot.send_message(admin_id, text, parse_mode="Markdown")
        except Exception:
            pass
    if GROUP_CHAT_ID:
        try:
            if photo_file_id:
                await bot.send_photo(GROUP_CHAT_ID, photo=photo_file_id, caption=text, parse_mode="Markdown")
            else:
                await bot.send_message(GROUP_CHAT_ID, text, parse_mode="Markdown")
        except Exception:
            pass


def is_admin(user_id: int) -> bool:
    return user_id in ALL_ADMINS

def is_superadmin(user_id: int) -> bool:
    return user_id in SUPERADMIN_IDS

def can_view_stats(user_id: int) -> bool:
    """Статистику могут смотреть все админы (управляющие + суперадмин)."""
    return user_id in ALL_ADMINS

def get_menu(user_id: int):
    if is_superadmin(user_id):
        return superadmin_menu()
    if is_admin(user_id):
        return admin_menu()
    return main_menu()

def fmt_time(s: str) -> str:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
    except Exception:
        return s

def now_str() -> str:
    return datetime.now(MSK).strftime("%d.%m.%Y %H:%M")


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    if is_superadmin(user_id):
        employee = await db.get_employee(user_id)
        if employee and employee["approved"]:
            await message.answer(f"👋 С возвращением, {employee['full_name']}!", reply_markup=superadmin_menu())
        else:
            await message.answer(
                "👋 Добро пожаловать, суперадмин!\n\n"
                "Для работы как сотрудник нужно зарегистрироваться.\n\n"
                "📝 Введите ваше *полное имя* (Фамилия Имя Отчество):",
                parse_mode="Markdown",
            )
            await state.set_state(Registration.waiting_name)
        return

    if is_admin(user_id):
        await message.answer("👋 Добро пожаловать!", reply_markup=admin_menu())
        return

    employee = await db.get_employee(user_id)
    if employee and employee["approved"]:
        await message.answer(f"👋 С возвращением, {employee['full_name']}!", reply_markup=main_menu())
        return
    if employee and not employee["approved"]:
        await message.answer("⏳ Ваша заявка ожидает одобрения администратора.")
        return

    await message.answer(
        "👋 Добро пожаловать в систему ПВЗ WB!\n\n"
        "Для работы нужно зарегистрироваться.\n\n"
        "📝 Введите ваше *полное имя* (Фамилия Имя Отчество):",
        parse_mode="Markdown",
    )
    await state.set_state(Registration.waiting_name)


# ── /chatid ───────────────────────────────────────────────────────────────────

@router.message(F.text == "/chatid")
async def cmd_chatid(message: Message):
    await message.answer(f"Chat ID: `{message.chat.id}`", parse_mode="Markdown")


# ── Регистрация ───────────────────────────────────────────────────────────────

@router.message(Registration.waiting_name)
async def reg_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 3:
        await message.answer("❗ Введите полное имя (минимум 3 символа).")
        return
    await state.update_data(full_name=name)
    await message.answer(
        f"✅ Имя: *{name}*\n\n🔢 Введите ваш *ID сотрудника WB PVZ*:",
        parse_mode="Markdown",
    )
    await state.set_state(Registration.waiting_wb_id)


@router.message(Registration.waiting_wb_id)
async def reg_wb_id(message: Message, state: FSMContext, bot: Bot):
    wb_id = message.text.strip()
    if not wb_id:
        await message.answer("❗ Введите ID сотрудника.")
        return

    data = await state.get_data()
    full_name = data["full_name"]
    telegram_id = message.from_user.id

    await db.register_employee(telegram_id, full_name, wb_id)

    if is_superadmin(telegram_id):
        await db.approve_employee(telegram_id)
        await state.clear()
        await message.answer(
            f"✅ Готово! Добро пожаловать, *{full_name}*!",
            parse_mode="Markdown",
            reply_markup=superadmin_menu(),
        )
        return

    await state.clear()
    await message.answer("✅ Заявка отправлена! Ожидайте одобрения администратора.")

    username = f"@{message.from_user.username}" if message.from_user.username else "нет"
    text = (
        f"🆕 *Новая заявка на регистрацию*\n\n"
        f"👤 Имя: {full_name}\n"
        f"🆔 Telegram ID: `{telegram_id}`\n"
        f"📱 Username: {username}\n"
        f"🏷 WB ID: `{wb_id}`"
    )
    for admin_id in SUPERADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="Markdown", reply_markup=approve_keyboard(telegram_id))
        except Exception:
            pass


# ── Одобрение / отклонение ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("approve:"))
async def cb_approve(callback: CallbackQuery, bot: Bot):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    telegram_id = int(callback.data.split(":")[1])
    await db.approve_employee(telegram_id)
    employee = await db.get_employee(telegram_id)
    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ Одобрено — {callback.from_user.full_name}",
        parse_mode="Markdown",
    )
    await callback.answer("Одобрено!")
    try:
        await bot.send_message(
            telegram_id,
            f"✅ Регистрация одобрена! Добро пожаловать, *{employee['full_name']}*!",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("reject:"))
async def cb_reject(callback: CallbackQuery, bot: Bot):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    telegram_id = int(callback.data.split(":")[1])
    await db.delete_employee(telegram_id)
    await callback.message.edit_text(
        callback.message.text + f"\n\n❌ Отклонено — {callback.from_user.full_name}",
        parse_mode="Markdown",
    )
    await callback.answer("Отклонено.")
    try:
        await bot.send_message(telegram_id, "❌ Ваша заявка отклонена. Обратитесь к руководителю.")
    except Exception:
        pass


# ── Guard ─────────────────────────────────────────────────────────────────────

async def check_approved(message: Message) -> bool:
    employee = await db.get_employee(message.from_user.id)
    if not employee:
        await message.answer("❗ Вы не зарегистрированы. Напишите /start")
        return False
    if not employee["approved"]:
        await message.answer("⏳ Ваша заявка ещё не одобрена.")
        return False
    return True


# ── Открытие смены ────────────────────────────────────────────────────────────

@router.message(F.text == "🟢 Открыть смену")
async def shift_open(message: Message, state: FSMContext):
    if not await check_approved(message):
        return
    active = await db.get_active_shift(message.from_user.id)
    if active:
        await message.answer("⚠️ У вас уже открыта смена. Сначала закройте её.")
        return
    await message.answer("📸 Пришлите фото ПВЗ для подтверждения открытия смены:")
    await state.set_state(ShiftOpen.waiting_photo)


@router.message(ShiftOpen.waiting_photo, F.photo)
async def shift_open_photo(message: Message, state: FSMContext, bot: Bot):
    employee = await db.get_employee(message.from_user.id)
    photo_id = message.photo[-1].file_id
    await db.open_shift(message.from_user.id, photo_id)
    await state.clear()
    now = now_str()
    await message.answer(
        f"✅ Смена открыта в {now}!\nХорошей работы, {employee['full_name']}! 💪",
        reply_markup=get_menu(message.from_user.id),
    )
    text = (
        f"🟢 *Смена открыта*\n\n"
        f"👤 Менеджер: {employee['full_name']}\n"
        f"🏷 WB ID: `{employee['wb_employee_id']}`\n"
        f"📍 ПВЗ: {PVZ_ADDRESS}\n"
        f"🕐 Время: {now}"
    )
    await notify_shift(bot, text, photo_id)


@router.message(ShiftOpen.waiting_photo)
async def shift_open_no_photo(message: Message):
    await message.answer("❗ Нужно именно *фото*. Отправьте фотографию.", parse_mode="Markdown")


# ── Закрытие смены ────────────────────────────────────────────────────────────

@router.message(F.text == "🔴 Закрыть смену")
async def shift_close(message: Message, state: FSMContext):
    if not await check_approved(message):
        return
    active = await db.get_active_shift(message.from_user.id)
    if not active:
        await message.answer("⚠️ Нет открытой смены.")
        return
    await message.answer("📸 Пришлите фото ПВЗ для подтверждения закрытия смены:")
    await state.set_state(ShiftClose.waiting_photo)


@router.message(ShiftClose.waiting_photo, F.photo)
async def shift_close_photo(message: Message, state: FSMContext, bot: Bot):
    active = await db.get_active_shift(message.from_user.id)
    if not active:
        await state.clear()
        await message.answer("⚠️ Нет открытой смены.")
        return
    employee = await db.get_employee(message.from_user.id)
    photo_id = message.photo[-1].file_id
    await db.close_shift(active["id"], photo_id)
    await state.clear()
    open_str = active["opened_at"]
    now = now_str()
    try:
        open_dt = datetime.strptime(open_str, "%Y-%m-%d %H:%M:%S")
        close_dt = datetime.now(MSK).replace(tzinfo=None)
        duration = int((close_dt - open_dt).total_seconds() // 60)
        hours, mins = divmod(duration, 60)
        dur_text = f"{hours}ч {mins}мин." if hours else f"{mins} мин."
    except Exception:
        dur_text = "—"
    await message.answer(
        f"🔴 Смена закрыта в {now}!\n\n"
        f"⏱ Открыта в {fmt_time(open_str)}, закрыта в {now.split(' ')[1]}\n"
        f"📊 Длительность: {dur_text}",
        reply_markup=get_menu(message.from_user.id),
    )
    text = (
        f"🔴 *Смена закрыта*\n\n"
        f"👤 Менеджер: {employee['full_name']}\n"
        f"🏷 WB ID: `{employee['wb_employee_id']}`\n"
        f"📍 ПВЗ: {PVZ_ADDRESS}\n"
        f"🕐 Открыта в {fmt_time(open_str)}, закрыта в {now.split(' ')[1]}\n"
        f"⏱ Длительность: {dur_text}"
    )
    await notify_shift(bot, text, photo_id)


@router.message(ShiftClose.waiting_photo)
async def shift_close_no_photo(message: Message):
    await message.answer("❗ Нужно именно *фото*. Отправьте фотографию.", parse_mode="Markdown")


# ── Перерыв: начало ───────────────────────────────────────────────────────────

@router.message(F.text == "☕ Взять перерыв")
async def break_start(message: Message, state: FSMContext):
    if not await check_approved(message):
        return
    active = await db.get_active_break(message.from_user.id)
    if active:
        await message.answer("⚠️ У вас уже активный перерыв. Сначала завершите его.")
        return
    await message.answer("📸 Пришлите фото для подтверждения начала перерыва:")
    await state.set_state(BreakStart.waiting_photo)


@router.message(BreakStart.waiting_photo, F.photo)
async def break_photo(message: Message, state: FSMContext, bot: Bot):
    employee = await db.get_employee(message.from_user.id)
    photo_id = message.photo[-1].file_id
    await db.start_break(message.from_user.id, photo_id)
    await state.clear()
    now = now_str()
    await message.answer(
        f"☕ Перерыв начат в {now}.\n\nНажмите «✅ Закончить перерыв» когда вернётесь.",
        reply_markup=get_menu(message.from_user.id),
    )
    text = (
        f"☕ *Перерыв начат*\n\n"
        f"👤 Менеджер: {employee['full_name']}\n"
        f"🏷 WB ID: `{employee['wb_employee_id']}`\n"
        f"📍 ПВЗ: {PVZ_ADDRESS}\n"
        f"🕐 Начало: {now}"
    )
    await notify_shift(bot, text, photo_id)


@router.message(BreakStart.waiting_photo)
async def break_no_photo(message: Message):
    await message.answer("❗ Нужно именно *фото*. Отправьте фотографию.", parse_mode="Markdown")


# ── Перерыв: конец ────────────────────────────────────────────────────────────

@router.message(F.text == "✅ Закончить перерыв")
async def break_end(message: Message, bot: Bot):
    if not await check_approved(message):
        return
    active = await db.get_active_break(message.from_user.id)
    if not active:
        await message.answer("⚠️ Нет активного перерыва.")
        return
    employee = await db.get_employee(message.from_user.id)
    await db.end_break(active["id"])
    updated = await db.get_break_by_id(active["id"])
    start_str = active["started_at"]
    end_str = updated["ended_at"]
    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
        duration = int((end_dt - start_dt).total_seconds() // 60)
        dur_text = f"{duration} мин."
    except Exception:
        dur_text = "—"
    await message.answer(
        f"✅ Перерыв завершён!\n\n⏱ С {fmt_time(start_str)} до {fmt_time(end_str)} ({dur_text})",
        reply_markup=get_menu(message.from_user.id),
    )
    text = (
        f"✅ *Перерыв завершён*\n\n"
        f"👤 Менеджер: {employee['full_name']}\n"
        f"🏷 WB ID: `{employee['wb_employee_id']}`\n"
        f"📍 ПВЗ: {PVZ_ADDRESS}\n"
        f"🕐 С {fmt_time(start_str)} до {fmt_time(end_str)}\n"
        f"⏱ Длительность: {dur_text}"
    )
    await notify_shift(bot, text, active["photo_file_id"])


# ── Список сотрудников ────────────────────────────────────────────────────────

@router.message(F.text == "👥 Список сотрудников")
async def list_employees(message: Message):
    if not is_superadmin(message.from_user.id):
        await message.answer("❗ Нет доступа.")
        return
    employees = await db.get_all_employees()
    if not employees:
        await message.answer("Сотрудников пока нет.")
        return
    lines = ["👥 *Список сотрудников:*\n"]
    for emp in employees:
        status = "✅" if emp["approved"] else "⏳"
        lines.append(
            f"{status} *{emp['full_name']}*\n"
            f"   TG: `{emp['telegram_id']}`\n"
            f"   WB ID: `{emp['wb_employee_id']}`\n"
            f"   Дата: {emp['registered_at']}\n"
        )
    await message.answer("\n".join(lines), parse_mode="Markdown")


# ── Статистика: выбор сотрудника ──────────────────────────────────────────────

@router.message(F.text == "📊 Статистика")
async def stats_pick_employee(message: Message):
    if not can_view_stats(message.from_user.id):
        await message.answer("❗ Нет доступа.")
        return
    employees = await db.get_approved_employees()
    if not employees:
        await message.answer("Одобренных сотрудников пока нет.")
        return
    await message.answer(
        "👤 Выберите сотрудника:",
        reply_markup=staff_picker_keyboard(employees),
    )


@router.callback_query(F.data.startswith("stat_emp:"))
async def stats_pick_type(callback: CallbackQuery):
    if not can_view_stats(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    telegram_id = int(callback.data.split(":")[1])
    employee = await db.get_employee(telegram_id)
    if not employee:
        await callback.answer("Сотрудник не найден.", show_alert=True)
        return
    await callback.message.edit_text(
        f"👤 *{employee['full_name']}*\n\nЧто показать?",
        parse_mode="Markdown",
        reply_markup=stat_type_keyboard(telegram_id),
    )
    await callback.answer()


# ── Статистика: смены за неделю ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("stat_shifts:"))
async def stats_shifts_week(callback: CallbackQuery):
    if not can_view_stats(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    telegram_id = int(callback.data.split(":")[1])
    employee = await db.get_employee(telegram_id)
    shifts = await db.get_shifts_this_week(telegram_id)

    if not shifts:
        await callback.message.edit_text(
            f"👤 *{employee['full_name']}*\n\n📅 Смен за эту неделю: *0*",
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    lines = [f"👤 *{employee['full_name']}*\n📅 Смены за эту неделю: *{len(shifts)}*\n"]
    for i, s in enumerate(shifts, 1):
        opened = fmt_time(s["opened_at"])
        date = s["opened_at"][:10] if s["opened_at"] else "—"
        try:
            date_fmt = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m")
        except Exception:
            date_fmt = date

        if s["closed_at"]:
            closed = fmt_time(s["closed_at"])
            try:
                open_dt = datetime.strptime(s["opened_at"], "%Y-%m-%d %H:%M:%S")
                close_dt = datetime.strptime(s["closed_at"], "%Y-%m-%d %H:%M:%S")
                mins = int((close_dt - open_dt).total_seconds() // 60)
                h, m = divmod(mins, 60)
                dur = f"{h}ч {m}м" if h else f"{m}м"
            except Exception:
                dur = "—"
            lines.append(f"{i}. {date_fmt} — {opened}–{closed} ({dur})")
        else:
            lines.append(f"{i}. {date_fmt} — {opened}–… (не закрыта)")

    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown")
    await callback.answer()


# ── Статистика: выбор дня для перерывов ──────────────────────────────────────

@router.callback_query(F.data.startswith("stat_breaks_days:"))
async def stats_breaks_pick_day(callback: CallbackQuery):
    if not can_view_stats(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    telegram_id = int(callback.data.split(":")[1])
    employee = await db.get_employee(telegram_id)
    days = await db.get_distinct_break_days(telegram_id)

    await callback.message.edit_text(
        f"👤 *{employee['full_name']}*\n\n☕ Выберите день:",
        parse_mode="Markdown",
        reply_markup=day_picker_keyboard(telegram_id, days),
    )
    await callback.answer()


# ── Статистика: перерывы за выбранный день ────────────────────────────────────

@router.callback_query(F.data.startswith("stat_breaks:"))
async def stats_breaks_day(callback: CallbackQuery):
    if not can_view_stats(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = callback.data.split(":")
    telegram_id = int(parts[1])
    day = parts[2]  # YYYY-MM-DD

    employee = await db.get_employee(telegram_id)
    breaks = await db.get_breaks_by_day(telegram_id, day)

    try:
        day_fmt = datetime.strptime(day, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        day_fmt = day

    if not breaks:
        await callback.message.edit_text(
            f"👤 *{employee['full_name']}*\n☕ Перерывы за {day_fmt}: *нет*",
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    total_mins = 0
    lines = [f"👤 *{employee['full_name']}*\n☕ Перерывы за {day_fmt}: *{len(breaks)}*\n"]
    for i, b in enumerate(breaks, 1):
        start = fmt_time(b["started_at"])
        if b["ended_at"]:
            end = fmt_time(b["ended_at"])
            try:
                s_dt = datetime.strptime(b["started_at"], "%Y-%m-%d %H:%M:%S")
                e_dt = datetime.strptime(b["ended_at"], "%Y-%m-%d %H:%M:%S")
                mins = int((e_dt - s_dt).total_seconds() // 60)
                total_mins += mins
                lines.append(f"{i}. {start}–{end} ({mins} мин.)")
            except Exception:
                lines.append(f"{i}. {start}–{end}")
        else:
            lines.append(f"{i}. {start}–… (активен)")

    if total_mins:
        h, m = divmod(total_mins, 60)
        total_str = f"{h}ч {m}мин." if h else f"{total_mins} мин."
        lines.append(f"\n⏱ Итого: {total_str}")

    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


# ── Fallback ──────────────────────────────────────────────────────────────────

@router.message()
async def fallback(message: Message):
    user_id = message.from_user.id
    if is_admin(user_id):
        return
    employee = await db.get_employee(user_id)
    if not employee:
        await message.answer("Напишите /start для регистрации.")
    elif not employee["approved"]:
        await message.answer("⏳ Ваша заявка ожидает одобрения.")
