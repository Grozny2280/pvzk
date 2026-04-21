from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart

from config import ADMIN_IDS, SUPERADMIN_IDS, PVZ_ADDRESS
import database as db
from keyboards import main_menu, admin_menu, approve_keyboard

router = Router()

ALL_ADMINS = ADMIN_IDS + SUPERADMIN_IDS


# ── FSM States ────────────────────────────────────────────────────────────────

class Registration(StatesGroup):
    waiting_name = State()
    waiting_wb_id = State()

class ShiftOpen(StatesGroup):
    waiting_photo = State()

class BreakStart(StatesGroup):
    waiting_photo = State()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def notify_admins(bot: Bot, text: str, photo_file_id: str = None):
    for admin_id in ALL_ADMINS:
        try:
            if photo_file_id:
                await bot.send_photo(admin_id, photo=photo_file_id, caption=text, parse_mode="Markdown")
            else:
                await bot.send_message(admin_id, text, parse_mode="Markdown")
        except Exception:
            pass

def is_admin(user_id: int) -> bool:
    return user_id in ALL_ADMINS

def is_superadmin(user_id: int) -> bool:
    return user_id in SUPERADMIN_IDS

def fmt_time(s: str) -> str:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
    except Exception:
        return s

def now_str() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M")


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if is_superadmin(user_id):
        await message.answer("👋 Добро пожаловать, суперадмин!", reply_markup=admin_menu())
        return

    if is_admin(user_id):
        await message.answer("👋 Добро пожаловать! Вы получаете уведомления по ПВЗ.")
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
    await message.answer("📸 Пришлите фото ПВЗ для подтверждения открытия смены:")
    await state.set_state(ShiftOpen.waiting_photo)


@router.message(ShiftOpen.waiting_photo, F.photo)
async def shift_open_photo(message: Message, state: FSMContext, bot: Bot):
    employee = await db.get_employee(message.from_user.id)
    photo_id = message.photo[-1].file_id

    await db.open_shift(message.from_user.id, photo_id)
    await state.clear()

    now = now_str()
    await message.answer(f"✅ Смена открыта в {now}! Хорошей работы, {employee['full_name']}! 💪", reply_markup=main_menu())

    text = (
        f"🟢 *Смена открыта*\n\n"
        f"👤 Менеджер: {employee['full_name']}\n"
        f"🏷 WB ID: `{employee['wb_employee_id']}`\n"
        f"📍 ПВЗ: {PVZ_ADDRESS}\n"
        f"🕐 Время: {now}"
    )
    await notify_admins(bot, text, photo_id)


@router.message(ShiftOpen.waiting_photo)
async def shift_open_no_photo(message: Message):
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
    await message.answer(f"☕ Перерыв начат в {now}.\n\nНажмите «✅ Закончить перерыв» когда вернётесь.", reply_markup=main_menu())

    text = (
        f"☕ *Перерыв начат*\n\n"
        f"👤 Менеджер: {employee['full_name']}\n"
        f"🏷 WB ID: `{employee['wb_employee_id']}`\n"
        f"📍 ПВЗ: {PVZ_ADDRESS}\n"
        f"🕐 Начало: {now}"
    )
    await notify_admins(bot, text, photo_id)


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
        reply_markup=main_menu(),
    )

    text = (
        f"✅ *Перерыв завершён*\n\n"
        f"👤 Менеджер: {employee['full_name']}\n"
        f"🏷 WB ID: `{employee['wb_employee_id']}`\n"
        f"📍 ПВЗ: {PVZ_ADDRESS}\n"
        f"🕐 С {fmt_time(start_str)} до {fmt_time(end_str)}\n"
        f"⏱ Длительность: {dur_text}"
    )
    await notify_admins(bot, text, active["photo_file_id"])


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
