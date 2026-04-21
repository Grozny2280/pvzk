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
        # Используем photo_open_file_id и closed_at
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

        # Миграция: добавить колонки если таблица shifts уже существует со старой схемой
        for col, definition in [
            ("closed_at", "TEXT"),
            ("photo_open_file_id", "TEXT"),
            ("photo_close_file_id", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE shifts ADD COLUMN {col} {definition}")
                await db.commit()
            except Exception:
                pass  # Колонка уже есть

        # Миграция старого поля photo_file_id -> photo_open_file_id
        try:
            await db.execute("UPDATE shifts SET photo_open_file_id = photo_file_id WHERE photo_open_file_id IS NULL AND photo_file_id IS NOT NULL")
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
        await db.execute("INSERT INTO breaks (telegram_id, photo_file_id) VALUES (?, ?)", (telegram_id, photo_file_id))
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
