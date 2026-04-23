import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "pvz.db")

MSK_TIME = "datetime('now', '+3 hours')"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS employees (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                wb_employee_id TEXT NOT NULL,
                registered_at TEXT DEFAULT ({MSK_TIME}),
                approved INTEGER DEFAULT 0
            )
        """)
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                opened_at TEXT DEFAULT ({MSK_TIME}),
                closed_at TEXT,
                photo_open_file_id TEXT,
                photo_close_file_id TEXT
            )
        """)
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS breaks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                started_at TEXT DEFAULT ({MSK_TIME}),
                ended_at TEXT,
                photo_file_id TEXT
            )
        """)
        await db.commit()

        # Миграции для старых БД
        for col, definition in [
            ("closed_at", "TEXT"),
            ("photo_open_file_id", "TEXT"),
            ("photo_close_file_id", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE shifts ADD COLUMN {col} {definition}")
                await db.commit()
            except Exception:
                pass
        try:
            await db.execute(
                "UPDATE shifts SET photo_open_file_id = photo_file_id "
                "WHERE photo_open_file_id IS NULL AND photo_file_id IS NOT NULL"
            )
            await db.commit()
        except Exception:
            pass


async def get_employee(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM employees WHERE telegram_id = ?", (telegram_id,)) as cur:
            return await cur.fetchone()


async def register_employee(telegram_id: int, full_name: str, wb_employee_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO employees (telegram_id, full_name, wb_employee_id, approved) VALUES (?, ?, ?, 0)",
            (telegram_id, full_name, wb_employee_id),
        )
        await db.commit()


async def approve_employee(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE employees SET approved = 1 WHERE telegram_id = ?", (telegram_id,))
        await db.commit()


async def delete_employee(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM employees WHERE telegram_id = ?", (telegram_id,))
        await db.commit()


async def get_all_employees():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM employees ORDER BY registered_at DESC") as cur:
            return await cur.fetchall()


async def get_approved_employees():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM employees WHERE approved = 1 ORDER BY full_name"
        ) as cur:
            return await cur.fetchall()


async def open_shift(telegram_id: int, photo_file_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO shifts (telegram_id, photo_open_file_id) VALUES (?, ?)",
            (telegram_id, photo_file_id)
        )
        await db.commit()


async def get_active_shift(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shifts WHERE telegram_id = ? AND closed_at IS NULL ORDER BY id DESC LIMIT 1",
            (telegram_id,),
        ) as cur:
            return await cur.fetchone()


async def close_shift(shift_id: int, photo_file_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE shifts SET closed_at = datetime('now', '+3 hours'), photo_close_file_id = ? WHERE id = ?",
            (photo_file_id, shift_id)
        )
        await db.commit()


async def get_shift_by_id(shift_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)) as cur:
            return await cur.fetchone()


async def get_active_break(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM breaks WHERE telegram_id = ? AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
            (telegram_id,),
        ) as cur:
            return await cur.fetchone()


async def start_break(telegram_id: int, photo_file_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO breaks (telegram_id, photo_file_id) VALUES (?, ?)",
            (telegram_id, photo_file_id)
        )
        await db.commit()


async def end_break(break_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE breaks SET ended_at = datetime('now', '+3 hours') WHERE id = ?",
            (break_id,)
        )
        await db.commit()


async def get_break_by_id(break_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM breaks WHERE id = ?", (break_id,)) as cur:
            return await cur.fetchone()


# ── Статистика ────────────────────────────────────────────────────────────────

async def get_shifts_this_week(telegram_id: int):
    """Смены с понедельника текущей недели по МСК."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM shifts
            WHERE telegram_id = ?
              AND date(opened_at) >= date(datetime('now', '+3 hours'), 'weekday 1', '-7 days')
            ORDER BY opened_at DESC
        """, (telegram_id,)) as cur:
            return await cur.fetchall()


async def get_breaks_for_week(telegram_id: int):
    """Перерывы с понедельника текущей недели по МСК."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM breaks
            WHERE telegram_id = ?
              AND date(started_at) >= date(datetime('now', '+3 hours'), 'weekday 1', '-7 days')
            ORDER BY started_at ASC
        """, (telegram_id,)) as cur:
            return await cur.fetchall()


async def get_breaks_by_day(telegram_id: int, day: str):
    """Перерывы за конкретный день (YYYY-MM-DD)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM breaks
            WHERE telegram_id = ?
              AND date(started_at) = ?
            ORDER BY started_at ASC
        """, (telegram_id, day)) as cur:
            return await cur.fetchall()


async def get_distinct_break_days(telegram_id: int):
    """Уникальные дни с перерывами за последние 30 дней."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT DISTINCT date(started_at) as day FROM breaks
            WHERE telegram_id = ?
              AND date(started_at) >= date(datetime('now', '+3 hours'), '-30 days')
            ORDER BY day DESC
        """, (telegram_id,)) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]
