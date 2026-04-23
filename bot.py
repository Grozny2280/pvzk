import asyncio
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, GROUP_CHAT_ID
from database import init_db
from handlers import router

logging.basicConfig(level=logging.INFO)

MSK = timezone(timedelta(hours=3))


async def send_weekly_report(bot: Bot):
    """Еженедельный отчёт по всем сотрудникам — смены + перерывы за неделю."""
    import database as db

    if not GROUP_CHAT_ID:
        return

    employees = await db.get_approved_employees()
    if not employees:
        return

    now = datetime.now(MSK)
    # Начало текущей недели (пн 00:00)
    monday = now - timedelta(days=now.weekday())
    week_start = monday.strftime("%d.%m")
    week_end = now.strftime("%d.%m.%Y")

    lines = [f"📊 *Итоги недели {week_start}–{week_end}*\n"]

    for emp in employees:
        tid = emp["telegram_id"]
        shifts = await db.get_shifts_this_week(tid)

        # Считаем суммарное время смен
        total_shift_mins = 0
        for s in shifts:
            if s["opened_at"] and s["closed_at"]:
                try:
                    o = datetime.strptime(s["opened_at"], "%Y-%m-%d %H:%M:%S")
                    c = datetime.strptime(s["closed_at"], "%Y-%m-%d %H:%M:%S")
                    total_shift_mins += int((c - o).total_seconds() // 60)
                except Exception:
                    pass

        # Перерывы за всю неделю
        breaks_week = await db.get_breaks_for_week(tid)
        total_break_mins = 0
        for b in breaks_week:
            if b["started_at"] and b["ended_at"]:
                try:
                    s_dt = datetime.strptime(b["started_at"], "%Y-%m-%d %H:%M:%S")
                    e_dt = datetime.strptime(b["ended_at"], "%Y-%m-%d %H:%M:%S")
                    total_break_mins += int((e_dt - s_dt).total_seconds() // 60)
                except Exception:
                    pass

        def fmt_mins(m):
            if m == 0:
                return "0м"
            h, mn = divmod(m, 60)
            return f"{h}ч {mn}м" if h else f"{mn}м"

        sh = len(shifts)
        br = len(breaks_week)

        lines.append(
            f"👤 *{emp['full_name']}*\n"
            f"   📅 Смен: {sh} ({fmt_mins(total_shift_mins)})\n"
            f"   ☕ Перерывов: {br} ({fmt_mins(total_break_mins)})\n"
        )

    if len(lines) == 1:
        lines.append("Активности за неделю не было.")

    text = "\n".join(lines)

    try:
        await bot.send_message(GROUP_CHAT_ID, text, parse_mode="Markdown")
        logging.info("Weekly report sent to group chat.")
    except Exception as e:
        logging.error(f"Failed to send weekly report: {e}")


async def weekly_report_scheduler(bot: Bot):
    """Ждёт воскресенья 21:00 МСК и отправляет отчёт."""
    while True:
        now = datetime.now(MSK)
        # weekday(): 6 = воскресенье
        days_until_sunday = (6 - now.weekday()) % 7
        next_sunday = now.replace(hour=21, minute=0, second=0, microsecond=0)
        if days_until_sunday > 0:
            next_sunday += timedelta(days=days_until_sunday)
        elif now.hour >= 21:
            # Уже после 21:00 в воскресенье — ждём следующее
            next_sunday += timedelta(days=7)

        wait_seconds = (next_sunday - now).total_seconds()
        logging.info(f"Next weekly report in {wait_seconds:.0f}s ({next_sunday.strftime('%d.%m %H:%M')} МСК)")
        await asyncio.sleep(wait_seconds)
        await send_weekly_report(bot)


async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Запускаем планировщик параллельно
    asyncio.create_task(weekly_report_scheduler(bot))

    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
