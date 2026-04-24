from datetime import datetime, timezone, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart, Command

from config import ADMIN_IDS, SUPERADMIN_IDS, PVZ_ADDRESS, GROUP_CHAT_ID
import database as db
from keyboards import (
    menu_default, menu_shift_open, menu_on_break, menu_admin, menu_cancel,
    approve_keyboard, staff_picker_keyboard, stat_type_keyboard, day_picker_keyboard,
)

router = Router()
ALL_ADMINS = ADMIN_IDS + SUPERADMIN_IDS
MSK = timezone(timedelta(hours=3))

BREAK_ALERT_MINUTES = 15


# ── FSM ───────────────────────────────────────────────────────────────────────

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

def is_admin(uid): return uid in ALL_ADMINS
def is_superadmin(uid): return uid in SUPERADMIN_IDS
def can_view_stats(uid): return uid in ALL_ADMINS

def fmt_time(s):
    try: return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
    except: return s

def now_str(): return datetime.now(MSK).strftime("%d.%m.%Y %H:%M")

def fmt_mins(m):
    if m == 0: return "0м"
    h, mn = divmod(m, 60)
    return f"{h}ч {mn}м" if h else f"{mn}м"

async def get_actual_menu(user_id):
    sa = is_superadmin(user_id)
    if is_admin(user_id) and not sa:
        return menu_admin()
    active_shift = await db.get_active_shift(user_id)
    if not active_shift:
        return menu_default(sa)
    active_break = await db.get_active_break(user_id)
    if active_break:
        return menu_on_break(sa)
    return menu_shift_open(sa)

async def send_to_chat(bot, text, photo=None):
    if not GROUP_CHAT_ID: return
    try:
        if photo: await bot.send_photo(GROUP_CHAT_ID, photo=photo, caption=text, parse_mode="Markdown")
        else: await bot.send_message(GROUP_CHAT_ID, text, parse_mode="Markdown")
    except Exception as e:
        import logging; logging.error(f"[CHAT ERROR] {e}")

async def notify_admins(bot, text, photo=None):
    for aid in ALL_ADMINS:
        try:
            if photo: await bot.send_photo(aid, photo=photo, caption=text, parse_mode="Markdown")
            else: await bot.send_message(aid, text, parse_mode="Markdown")
        except: pass

# СМЕНЫ — теперь ТОЛЬКО в личку админам (НЕ в чат)
async def notify_shift(bot, text, photo=None):
    await notify_admins(bot, text, photo)

# Перерыв в чат — только если > 15 минут
async def notify_break_end(bot, text, photo=None, duration_mins: int = 0):
    await notify_admins(bot, text, photo)
    if duration_mins > BREAK_ALERT_MINUTES:
        await send_to_chat(bot, text, photo)


async def build_weekly_report() -> str:
    employees = await db.get_approved_employees()
    now = datetime.now(MSK)
    monday = now - timedelta(days=now.weekday())
    lines = [f"📊 *Итоги недели {monday.strftime('%d.%m')}–{now.strftime('%d.%m.%Y')}*\n"]
    if not employees:
        lines.append("Сотрудников пока нет.")
        return "\n".join(lines)
    for emp in employees:
        tid = emp["telegram_id"]
        shifts = await db.get_shifts_this_week(tid)
        breaks = await db.get_breaks_for_week(tid)
        sm = sum(
            int((datetime.strptime(s["closed_at"], "%Y-%m-%d %H:%M:%S") -
                 datetime.strptime(s["opened_at"], "%Y-%m-%d %H:%M:%S")).total_seconds() // 60)
            for s in shifts if s["opened_at"] and s["closed_at"]
        )
        bm = sum(
            int((datetime.strptime(b["ended_at"], "%Y-%m-%d %H:%M:%S") -
                 datetime.strptime(b["started_at"], "%Y-%m-%d %H:%M:%S")).total_seconds() // 60)
            for b in breaks if b["started_at"] and b["ended_at"]
        )
        lines.append(
            f"👤 *{emp['full_name']}*\n"
            f"   📅 Смен: {len(shifts)} ({fmt_mins(sm)})\n"
            f"   ☕ Перерывов: {len(breaks)} ({fmt_mins(bm)})\n"
        )
    return "\n".join(lines)


async def try_send_sunday_report(bot: Bot):
    """Вызывается при каждом закрытии смены в воскресенье."""
    now = datetime.now(MSK)
    if now.weekday() != 6:
        return
    remaining = await db.count_active_shifts()
    if remaining > 0:
        return
    text = await build_weekly_report()
    await send_to_chat(bot, text)
    await notify_admins(bot, text)
    import logging
    logging.info("Sunday weekly report sent after last shift closed.")


# ── Отмена ────────────────────────────────────────────────────────────────────

@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("↩️ Отменено.", reply_markup=await get_actual_menu(message.from_user.id))


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    if is_superadmin(uid):
        emp = await db.get_employee(uid)
        if emp and emp["approved"]:
            await message.answer(f"👋 С возвращением, {emp['full_name']}!", reply_markup=await get_actual_menu(uid))
        else:
            await message.answer("👋 Добро пожаловать, суперадмин!\n\n📝 Введите ваше *полное имя*:", parse_mode="Markdown", reply_markup=menu_cancel())
            await state.set_state(Registration.waiting_name)
        return
    if is_admin(uid):
        await message.answer("👋 Добро пожаловать!", reply_markup=menu_admin())
        return
    emp = await db.get_employee(uid)
    if emp and emp["approved"]:
        await message.answer(f"👋 С возвращением, {emp['full_name']}!", reply_markup=await get_actual_menu(uid))
    elif emp:
        await message.answer("⏳ Ваша заявка ожидает одобрения.")
    else:
        await message.answer("👋 Добро пожаловать!\n\n📝 Введите ваше *полное имя* (ФИО):", parse_mode="Markdown", reply_markup=menu_cancel())
        await state.set_state(Registration.waiting_name)


# ── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    uid = message.from_user.id
    lines = ["📋 *Список команд и кнопок*\n"]

    lines.append(
        "⌨️ *Команды:*\n"
        "/start — запустить бота / вернуть меню\n"
        "/help — список всех команд\n"
        "/active — кто сейчас на смене\n"
    )

    if can_view_stats(uid):
        lines.append(
            "/weekly\\_report — итоги недели вручную\n"
            "/chatid — узнать ID чата (для настройки)\n"
        )

    lines.append("\n🔘 *Кнопки менеджера:*\n")
    lines.append(
        "🟢 *Открыть смену* — начало рабочего дня, нужно фото ПВЗ\n"
        "☕ *Взять перерыв* — фиксирует начало перерыва + фото\n"
        "✅ *Закончить перерыв* — закрывает перерыв, считает время\n"
        "🔴 *Закрыть смену* — конец рабочего дня, нужно фото ПВЗ\n"
        "👁 *Активные смены* — кто сейчас работает\n"
    )

    if can_view_stats(uid):
        lines.append(
            "\n🔘 *Кнопки администратора:*\n"
            "👥 *Список сотрудников* — все зарегистрированные\n"
            "📊 *Статистика* — смены и перерывы по сотруднику\n"
        )

    lines.append(
        f"\n📣 *Уведомления:*\n"
        "• Открытие/закрытие смены → только в личку админам\n"
        "• Перерыв начат → только в личку админам\n"
        f"• Перерыв завершён > {BREAK_ALERT_MINUTES} мин → в чат с предупреждением\n"
        "• Итоги недели → воскресенье после последней смены (в чат и админам)\n"
    )

    await message.answer("\n".join(lines), parse_mode="Markdown")


# ── /active и кнопка 👁 Активные смены ───────────────────────────────────────

async def show_active_shifts(message: Message):
    shifts = await db.get_all_active_shifts()
    if not shifts:
        await message.answer("😴 Сейчас нет открытых смен.")
        return
    now = datetime.now(MSK)
    lines = [f"👁 *Активные смены ({len(shifts)}):*\n"]
    for s in shifts:
        try:
            opened = datetime.strptime(s["opened_at"], "%Y-%m-%d %H:%M:%S")
            dur = int((now.replace(tzinfo=None) - opened).total_seconds() // 60)
            dur_text = fmt_mins(dur)
        except:
            dur_text = "—"
        on_break = await db.get_active_break(s["telegram_id"])
        status = "☕ на перерыве" if on_break else "🟢 работает"
        lines.append(
            f"• *{s['full_name']}*  {status}\n"
            f"  С {fmt_time(s['opened_at'])} ({dur_text})"
        )
    await message.answer("\n".join(lines), parse_mode="Markdown")

@router.message(Command("active"))
async def cmd_active(message: Message):
    await show_active_shifts(message)

@router.message(F.text == "👁 Активные смены")
async def btn_active_shifts(message: Message):
    await show_active_shifts(message)


# ── /weekly_report ────────────────────────────────────────────────────────────

@router.message(Command("weekly_report"))
async def cmd_weekly_report(message: Message, bot: Bot):
    if not can_view_stats(message.from_user.id):
        await message.answer("❗ Нет доступа."); return
    await message.answer("⏳ Формирую отчёт...")
    text = await build_weekly_report()
    await send_to_chat(bot, text)
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("chatid"))
async def cmd_chatid(message: Message):
    await message.answer(f"Chat ID: `{message.chat.id}`", parse_mode="Markdown")


# ── Регистрация ───────────────────────────────────────────────────────────────

@router.message(Registration.waiting_name)
async def reg_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 3:
        await message.answer("❗ Минимум 3 символа."); return
    await state.update_data(full_name=name)
    await message.answer(f"✅ Имя: *{name}*\n\n🔢 Введите *ID сотрудника WB PVZ*:", parse_mode="Markdown", reply_markup=menu_cancel())
    await state.set_state(Registration.waiting_wb_id)

@router.message(Registration.waiting_wb_id)
async def reg_wb_id(message: Message, state: FSMContext, bot: Bot):
    wb_id = message.text.strip()
    if not wb_id:
        await message.answer("❗ Введите ID."); return
    data = await state.get_data()
    full_name = data["full_name"]
    tid = message.from_user.id
    await db.register_employee(tid, full_name, wb_id)
    if is_superadmin(tid):
        await db.approve_employee(tid)
        await state.clear()
        await message.answer(f"✅ Добро пожаловать, *{full_name}*!", parse_mode="Markdown", reply_markup=menu_default(True))
        return
    await state.clear()
    await message.answer("✅ Заявка отправлена! Ожидайте одобрения.")
    username = f"@{message.from_user.username}" if message.from_user.username else "нет"
    text = f"🆕 *Новая заявка*\n\n👤 {full_name}\n🆔 `{tid}`\n📱 {username}\n🏷 `{wb_id}`"
    for aid in SUPERADMIN_IDS:
        try: await bot.send_message(aid, text, parse_mode="Markdown", reply_markup=approve_keyboard(tid))
        except: pass


# ── Одобрение / отклонение ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("approve:"))
async def cb_approve(callback: CallbackQuery, bot: Bot):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True); return
    tid = int(callback.data.split(":")[1])
    await db.approve_employee(tid)
    emp = await db.get_employee(tid)
    await callback.message.edit_text(callback.message.text + f"\n\n✅ Одобрено — {callback.from_user.full_name}", parse_mode="Markdown")
    await callback.answer("Одобрено!")
    try: await bot.send_message(tid, f"✅ Добро пожаловать, *{emp['full_name']}*!", parse_mode="Markdown", reply_markup=menu_default())
    except: pass

@router.callback_query(F.data.startswith("reject:"))
async def cb_reject(callback: CallbackQuery, bot: Bot):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True); return
    tid = int(callback.data.split(":")[1])
    await db.delete_employee(tid)
    await callback.message.edit_text(callback.message.text + f"\n\n❌ Отклонено — {callback.from_user.full_name}", parse_mode="Markdown")
    await callback.answer("Отклонено.")
    try: await bot.send_message(tid, "❌ Заявка отклонена. Обратитесь к руководителю.")
    except: pass


# ── Guard ─────────────────────────────────────────────────────────────────────

async def check_approved(message: Message):
    emp = await db.get_employee(message.from_user.id)
    if not emp:
        await message.answer("❗ Не зарегистрированы. Напишите /start"); return False
    if not emp["approved"]:
        await message.answer("⏳ Заявка ещё не одобрена."); return False
    return True


# ── Открытие смены ────────────────────────────────────────────────────────────

@router.message(F.text == "🟢 Открыть смену")
async def shift_open(message: Message, state: FSMContext):
    if not await check_approved(message): return
    if await db.get_active_shift(message.from_user.id):
        await message.answer("⚠️ Смена уже открыта."); return
    await message.answer("📸 Пришлите фото ПВЗ для открытия смены:", reply_markup=menu_cancel())
    await state.set_state(ShiftOpen.waiting_photo)

@router.message(ShiftOpen.waiting_photo, F.photo)
async def shift_open_photo(message: Message, state: FSMContext, bot: Bot):
    emp = await db.get_employee(message.from_user.id)
    photo_id = message.photo[-1].file_id
    await db.open_shift(message.from_user.id, photo_id)
    await state.clear()
    now = now_str()
    await message.answer(
        f"✅ Смена открыта в {now}!\nХорошей работы, {emp['full_name']}! 💪",
        reply_markup=menu_shift_open(is_superadmin(message.from_user.id))
    )
    await notify_shift(
        bot,
        f"🟢 *Смена открыта*\n\n👤 {emp['full_name']}\n🏷 `{emp['wb_employee_id']}`\n📍 {PVZ_ADDRESS}\n🕐 {now}",
        photo_id
    )

@router.message(ShiftOpen.waiting_photo)
async def shift_open_no_photo(message: Message):
    await message.answer("❗ Нужно фото или нажмите ❌ Отмена.")


# ── Закрытие смены ────────────────────────────────────────────────────────────

@router.message(F.text == "🔴 Закрыть смену")
async def shift_close(message: Message, state: FSMContext):
    if not await check_approved(message): return
    if await db.get_active_break(message.from_user.id):
        await message.answer("⚠️ Сначала завершите перерыв."); return
    active = await db.get_active_shift(message.from_user.id)
    if not active:
        await message.answer("⚠️ Нет открытой смены.", reply_markup=await get_actual_menu(message.from_user.id)); return
    await message.answer("📸 Пришлите фото ПВЗ для закрытия смены:", reply_markup=menu_cancel())
    await state.set_state(ShiftClose.waiting_photo)

@router.message(ShiftClose.waiting_photo, F.photo)
async def shift_close_photo(message: Message, state: FSMContext, bot: Bot):
    active = await db.get_active_shift(message.from_user.id)
    if not active:
        await state.clear(); await message.answer("⚠️ Нет открытой смены."); return
    emp = await db.get_employee(message.from_user.id)
    photo_id = message.photo[-1].file_id
    await db.close_shift(active["id"], photo_id)
    await state.clear()
    open_str = active["opened_at"]
    now = now_str()
    try:
        open_dt = datetime.strptime(open_str, "%Y-%m-%d %H:%M:%S")
        close_dt = datetime.now(MSK).replace(tzinfo=None)
        dur = int((close_dt - open_dt).total_seconds() // 60)
        h, m = divmod(dur, 60)
        dur_text = f"{h}ч {m}мин." if h else f"{m} мин."
    except: dur_text = "—"

    await message.answer(
        f"🔴 Смена закрыта в {now}!\n⏱ {fmt_time(open_str)}–{now.split(' ')[1]} ({dur_text})",
        reply_markup=menu_default(is_superadmin(message.from_user.id))
    )
    await notify_shift(
        bot,
        f"🔴 *Смена закрыта*\n\n👤 {emp['full_name']}\n🏷 `{emp['wb_employee_id']}`\n📍 {PVZ_ADDRESS}\n🕐 {fmt_time(open_str)}–{now.split(' ')[1]}\n⏱ {dur_text}",
        photo_id
    )

    await try_send_sunday_report(bot)

@router.message(ShiftClose.waiting_photo)
async def shift_close_no_photo(message: Message):
    await message.answer("❗ Нужно фото или нажмите ❌ Отмена.")


# ── Перерыв: начало ───────────────────────────────────────────────────────────

@router.message(F.text == "☕ Взять перерыв")
async def break_start(message: Message, state: FSMContext):
    if not await check_approved(message): return
    if not await db.get_active_shift(message.from_user.id):
        await message.answer("⚠️ Сначала откройте смену.", reply_markup=await get_actual_menu(message.from_user.id)); return
    if await db.get_active_break(message.from_user.id):
        await message.answer("⚠️ Перерыв уже активен."); return
    await message.answer("📸 Пришлите фото для начала перерыва:", reply_markup=menu_cancel())
    await state.set_state(BreakStart.waiting_photo)

@router.message(BreakStart.waiting_photo, F.photo)
async def break_photo(message: Message, state: FSMContext, bot: Bot):
    emp = await db.get_employee(message.from_user.id)
    photo_id = message.photo[-1].file_id
    await db.start_break(message.from_user.id, photo_id)
    await state.clear()
    now = now_str()
    await message.answer(
        f"☕ Перерыв начат в {now}.\n\nНажмите «✅ Закончить перерыв» когда вернётесь.",
        reply_markup=menu_on_break(is_superadmin(message.from_user.id))
    )
    await notify_admins(
        bot,
        f"☕ *Перерыв начат*\n\n👤 {emp['full_name']}\n🏷 `{emp['wb_employee_id']}`\n📍 {PVZ_ADDRESS}\n🕐 {now}",
        photo_id
    )

@router.message(BreakStart.waiting_photo)
async def break_no_photo(message: Message):
    await message.answer("❗ Нужно фото или нажмите ❌ Отмена.")


# ── Перерыв: конец ────────────────────────────────────────────────────────────

@router.message(F.text == "✅ Закончить перерыв")
async def break_end(message: Message, bot: Bot):
    if not await check_approved(message): return
    active = await db.get_active_break(message.from_user.id)
    if not active:
        await message.answer("⚠️ Нет активного перерыва.", reply_markup=await get_actual_menu(message.from_user.id)); return
    emp = await db.get_employee(message.from_user.id)
    await db.end_break(active["id"])
    updated = await db.get_break_by_id(active["id"])
    start_str, end_str = active["started_at"], updated["ended_at"]
    try:
        dur = int((
            datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S") -
            datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        ).total_seconds() // 60)
        dur_text = f"{dur} мин."
    except:
        dur = 0
        dur_text = "—"

    await message.answer(
        f"✅ Перерыв завершён!\n⏱ {fmt_time(start_str)}–{fmt_time(end_str)} ({dur_text})",
        reply_markup=menu_shift_open(is_superadmin(message.from_user.id))
    )

    alert = f"\n⚠️ *Перерыв превысил {BREAK_ALERT_MINUTES} минут!*" if dur > BREAK_ALERT_MINUTES else ""
    text = (
        f"✅ *Перерыв завершён*{alert}\n\n"
        f"👤 {emp['full_name']}\n"
        f"🏷 `{emp['wb_employee_id']}`\n"
        f"📍 {PVZ_ADDRESS}\n"
        f"🕐 {fmt_time(start_str)}–{fmt_time(end_str)}\n"
        f"⏱ {dur_text}"
    )
    await notify_break_end(bot, text, active["photo_file_id"], duration_mins=dur)


# ── Список сотрудников ────────────────────────────────────────────────────────

@router.message(F.text == "👥 Список сотрудников")
async def list_employees(message: Message):
    if not is_superadmin(message.from_user.id):
        await message.answer("❗ Нет доступа."); return
    employees = await db.get_all_employees()
    if not employees:
        await message.answer("Сотрудников пока нет."); return
    lines = ["👥 *Список сотрудников:*\n"]
    for emp in employees:
        status = "✅" if emp["approved"] else "⏳"
        lines.append(f"{status} *{emp['full_name']}*\n   TG: `{emp['telegram_id']}`\n   WB ID: `{emp['wb_employee_id']}`\n   Дата: {emp['registered_at']}\n")
    await message.answer("\n".join(lines), parse_mode="Markdown")


# ── Статистика ────────────────────────────────────────────────────────────────

@router.message(F.text == "📊 Статистика")
async def stats_pick_employee(message: Message):
    if not can_view_stats(message.from_user.id):
        await message.answer("❗ Нет доступа."); return
    employees = await db.get_approved_employees()
    if not employees:
        await message.answer("Одобренных сотрудников нет."); return
    await message.answer("👤 Выберите сотрудника:", reply_markup=staff_picker_keyboard(employees))

@router.callback_query(F.data.startswith("stat_emp:"))
async def stats_pick_type(callback: CallbackQuery):
    if not can_view_stats(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True); return
    tid = int(callback.data.split(":")[1])
    emp = await db.get_employee(tid)
    if not emp:
        await callback.answer("Не найден.", show_alert=True); return
    await callback.message.edit_text(f"👤 *{emp['full_name']}*\n\nЧто показать?", parse_mode="Markdown", reply_markup=stat_type_keyboard(tid))
    await callback.answer()

@router.callback_query(F.data.startswith("stat_shifts:"))
async def stats_shifts_week(callback: CallbackQuery):
    if not can_view_stats(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True); return
    tid = int(callback.data.split(":")[1])
    emp = await db.get_employee(tid)
    shifts = await db.get_shifts_this_week(tid)
    if not shifts:
        await callback.message.edit_text(f"👤 *{emp['full_name']}*\n\n📅 Смен за неделю: *0*", parse_mode="Markdown")
        await callback.answer(); return
    lines = [f"👤 *{emp['full_name']}*\n📅 Смены за неделю: *{len(shifts)}*\n"]
    for i, s in enumerate(shifts, 1):
        try: df = datetime.strptime(s["opened_at"][:10], "%Y-%m-%d").strftime("%d.%m")
        except: df = "—"
        if s["closed_at"]:
            try:
                mins = int((datetime.strptime(s["closed_at"], "%Y-%m-%d %H:%M:%S") - datetime.strptime(s["opened_at"], "%Y-%m-%d %H:%M:%S")).total_seconds() // 60)
                h, m = divmod(mins, 60)
                dur = f"{h}ч {m}м" if h else f"{m}м"
            except: dur = "—"
            lines.append(f"{i}. {df} — {fmt_time(s['opened_at'])}–{fmt_time(s['closed_at'])} ({dur})")
        else:
            lines.append(f"{i}. {df} — {fmt_time(s['opened_at'])}–… (не закрыта)")
    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("stat_breaks_days:"))
async def stats_breaks_pick_day(callback: CallbackQuery):
    if not can_view_stats(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True); return
    tid = int(callback.data.split(":")[1])
    emp = await db.get_employee(tid)
    days = await db.get_distinct_break_days(tid)
    await callback.message.edit_text(f"👤 *{emp['full_name']}*\n\n☕ Выберите день:", parse_mode="Markdown", reply_markup=day_picker_keyboard(tid, days))
    await callback.answer()

@router.callback_query(F.data.startswith("stat_breaks:"))
async def stats_breaks_day(callback: CallbackQuery):
    if not can_view_stats(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True); return
    parts = callback.data.split(":")
    tid, day = int(parts[1]), parts[2]
    emp = await db.get_employee(tid)
    breaks = await db.get_breaks_by_day(tid, day)
    try: day_fmt = datetime.strptime(day, "%Y-%m-%d").strftime("%d.%m.%Y")
    except: day_fmt = day
    if not breaks:
        await callback.message.edit_text(f"👤 *{emp['full_name']}*\n☕ Перерывы за {day_fmt}: *нет*", parse_mode="Markdown")
        await callback.answer(); return
    total = 0
    lines = [f"👤 *{emp['full_name']}*\n☕ Перерывы за {day_fmt}: *{len(breaks)}*\n"]
    for i, b in enumerate(breaks, 1):
        if b["ended_at"]:
            try:
                mins = int((datetime.strptime(b["ended_at"], "%Y-%m-%d %H:%M:%S") - datetime.strptime(b["started_at"], "%Y-%m-%d %H:%M:%S")).total_seconds() // 60)
                total += mins
                lines.append(f"{i}. {fmt_time(b['started_at'])}–{fmt_time(b['ended_at'])} ({mins} мин.)")
            except: lines.append(f"{i}. {fmt_time(b['started_at'])}–{fmt_time(b['ended_at'])}")
        else:
            lines.append(f"{i}. {fmt_time(b['started_at'])}–… (активен)")
    if total: lines.append(f"\n⏱ Итого: {fmt_mins(total)}")
    await callback.message.edit_text("\n".join(lines), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


# ── Fallback ──────────────────────────────────────────────────────────────────

@router.message()
async def fallback(message: Message):
    uid = message.from_user.id
    if is_admin(uid): return
    emp = await db.get_employee(uid)
    if not emp: await message.answer("Напишите /start для регистрации.")
    elif not emp["approved"]: await message.answer("⏳ Заявка ожидает одобрения.")
