# Полный код проекта

Ниже собраны все текстовые файлы проекта по отдельности.

# ===== .env.example =====
```text
BOT_TOKEN=1234567890:YOUR_TELEGRAM_BOT_TOKEN
ADMIN_ID=123456789
TIMEZONE=Europe/Moscow
WORK_START=10:00
WORK_END=20:00
LUNCH_START=14:00
LUNCH_END=15:00
BUFFER_MINUTES=15
BOOKING_DAYS=14
CANCELLATION_CUTOFF_HOURS=3
REMINDER_24_HOURS=24
REMINDER_2_HOURS=2
REVIEW_DELAY_MINUTES=150
DB_PATH=data/bot.db
MASTER_NAME=Мастер маникюра
CONTACTS_TEXT=📍 Адрес: укажите адрес\n💬 Для связи: @your_username

```

# ===== .gitignore =====
```text
__pycache__/
*.py[cod]
.venv/
.env
data/*.db
data/*.db-wal
data/*.db-shm
*.log

```

# ===== Procfile =====
```text
worker: python main.py

```

# ===== README.md =====
```markdown
# Telegram-бот онлайн-записи на маникюр

Стек: Python 3.11+, aiogram 3.31.0, SQLite + aiosqlite. Бот работает через long polling.

## Локальный запуск

1. Установить Python 3.11+.
2. Создать виртуальное окружение и установить зависимости:

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
```

3. Задать переменные окружения `BOT_TOKEN` и `ADMIN_ID`.
4. Запустить:

```bash
python main.py
```

База создастся автоматически как `data/bot.db`.

## Koyeb

Загрузить проект в GitHub и создать Worker-сервис. В переменных окружения Koyeb задать:

- `BOT_TOKEN` — токен BotFather;
- `ADMIN_ID` — Telegram ID владельца/администратора.

Koyeb увидит `Procfile` и запустит `worker: python main.py`.

Для SQLite держите одну реплику/один worker: база является локальным файлом экземпляра. Для полноценного продакшена с несколькими репликами лучше перейти на PostgreSQL.

## Важные настройки

Все рабочие параметры находятся в `config.py` и могут быть переопределены переменными окружения.

Начальные услуги находятся в `config.py` и автоматически создаются при первом запуске пустой БД. После этого ими можно управлять из `/admin`.

```

# ===== DATABASE_SCHEMA.md =====
```markdown
# Схема базы данных

База: SQLite. Доступ: `aiosqlite`.

## 1. users
Хранит Telegram-профиль клиента.

| Поле | Тип | Назначение |
|---|---|---|
| id | INTEGER PK | Telegram ID |
| username | TEXT | username без `@` |
| full_name | TEXT | Имя из Telegram |
| created_at | TEXT | Дата создания записи |
| updated_at | TEXT | Дата последнего обновления |

## 2. services
Справочник услуг мастера.

| Поле | Тип | Назначение |
|---|---|---|
| id | INTEGER PK | ID услуги |
| name | TEXT | Название |
| price | INTEGER | Цена в рублях |
| duration_min | INTEGER | Длительность в минутах |
| is_active | INTEGER | 1 — доступна, 0 — отключена |
| sort_order | INTEGER | Порядок вывода |

## 3. appointments
Записи клиентов.

| Поле | Тип | Назначение |
|---|---|---|
| id | INTEGER PK | ID записи |
| user_id | INTEGER FK | Клиент |
| service_id | INTEGER FK | Услуга |
| appointment_date | TEXT | Дата `YYYY-MM-DD` |
| start_time | TEXT | Начало `HH:MM` |
| end_time | TEXT | Окончание `HH:MM` |
| status | TEXT | Сейчас используются `confirmed` / `cancelled` |
| comment | TEXT | Пожелания клиента |
| created_at | TEXT | Создание |
| updated_at | TEXT | Изменение |
| remind_24_sent | INTEGER | Отправлено ли напоминание за 24 ч |
| remind_2_sent | INTEGER | Отправлено ли напоминание за 2 ч |
| review_requested | INTEGER | Отправлен ли запрос отзыва |

Защита от дублей: уникальный частичный индекс на `(appointment_date, start_time)` для `status='confirmed'`, плюс проверка пересечений и буфера внутри транзакции.

## 4. blocked_times
Временные интервалы, которые мастер закрыл для записи.

Поля: `id`, `block_date`, `start_time`, `end_time`, `reason`, `created_at`.

## 5. waiting_list
Заявки в листе ожидания.

Поля: `id`, `user_id`, `service_id`, `preferred_date`, `created_at`, `notified_at`, `status`.

Статусы: `active`, `notified`, `cancelled`.

## 6. reviews
Отзывы после визита.

| Поле | Тип | Назначение |
|---|---|---|
| id | INTEGER PK | ID отзыва |
| appointment_id | INTEGER UNIQUE FK | Какая запись |
| user_id | INTEGER FK | Клиент |
| rating | INTEGER | 1–5 |
| text | TEXT | Текст |
| created_at | TEXT | Время отзыва |

Уникальность `appointment_id` не позволяет оставить два отзыва к одной записи.

## 7. blacklist
Чёрный список.

Поля: `user_id` PK/FK, `reason`, `created_at`.

## Связи

```text
users 1 ───── N appointments N ───── 1 services
users 1 ───── N waiting_list N ───── 1 services
users 1 ───── N reviews 1 ────────── 1 appointments
users 1 ───── 1 blacklist
```

Дополнительно расписание не хранится в отдельной таблице: рабочие дни, часы, обед и буфер задаются в `config.py`. Доступные слоты рассчитываются динамически на основе этих настроек, записей и блокировок.

```

# ===== config.py =====
```python
import os
from zoneinfo import ZoneInfo

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

TIMEZONE_NAME = os.getenv("TIMEZONE", "Europe/Moscow")
TIMEZONE = ZoneInfo(TIMEZONE_NAME)

WORKING_DAYS = (1, 2, 3, 4, 5)  # Tuesday-Saturday in Python's weekday numbering (Mon=0)
WORK_START = os.getenv("WORK_START", "10:00")
WORK_END = os.getenv("WORK_END", "20:00")
LUNCH_START = os.getenv("LUNCH_START", "14:00")
LUNCH_END = os.getenv("LUNCH_END", "15:00")
BUFFER_MINUTES = int(os.getenv("BUFFER_MINUTES", "15"))
BOOKING_DAYS = int(os.getenv("BOOKING_DAYS", "14"))
CANCELLATION_CUTOFF_HOURS = int(os.getenv("CANCELLATION_CUTOFF_HOURS", "3"))
REMINDER_24_HOURS = int(os.getenv("REMINDER_24_HOURS", "24"))
REMINDER_2_HOURS = int(os.getenv("REMINDER_2_HOURS", "2"))
REVIEW_DELAY_MINUTES = int(os.getenv("REVIEW_DELAY_MINUTES", "150"))

DB_PATH = os.getenv("DB_PATH", "data/bot.db")

MASTER_NAME = os.getenv("MASTER_NAME", "Мастер маникюра")
CONTACTS_TEXT = os.getenv(
    "CONTACTS_TEXT",
    "📍 Адрес: укажите адрес мастера в переменной CONTACTS_TEXT\n"
    "💬 Для связи: напишите мастеру в Telegram.",
)

DEFAULT_SERVICES = (
    ("Классический маникюр", 1500, 60),
    ("Аппаратный маникюр", 1800, 90),
    ("Маникюр + покрытие гель-лак", 2200, 120),
    ("Снятие покрытия", 500, 30),
    ("Укрепление гелем", 800, 40),
)

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения")
if not ADMIN_ID:
    raise RuntimeError("Не задан ADMIN_ID в переменных окружения")

```

# ===== main.py =====
```python
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, TIMEZONE_NAME
from database.db import Database
from handlers.admin import router as admin_router
from handlers.common import router as common_router
from handlers.user import router as user_router
from middlewares.throttling import SimpleThrottleMiddleware
from services.reminders import reminders_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Запуск бота. Часовой пояс: %s", TIMEZONE_NAME)
    db = Database()
    await db.connect()
    await db.init_schema()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.workflow_data["db"] = db

    # All incoming events get a small anti-spam throttle.
    dp.message.middleware(SimpleThrottleMiddleware())
    dp.callback_query.middleware(SimpleThrottleMiddleware())

    dp.include_router(common_router)
    dp.include_router(user_router)
    dp.include_router(admin_router)

    reminder_task = asyncio.create_task(reminders_loop(bot, db), name="reminders")

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        me = await bot.get_me()
        logger.info("Бот @%s готов. Long polling запущен.", me.username)
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        await asyncio.gather(reminder_task, return_exceptions=True)
        await db.close()
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Завершение по сигналу")

```

# ===== database/__init__.py =====
```python
from .db import Database

__all__ = ["Database"]

```

# ===== database/models.py =====
```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Service:
    id: int
    name: str
    price: int
    duration_min: int
    is_active: int = 1


@dataclass(slots=True)
class Appointment:
    id: int
    user_id: int
    service_id: int
    service_name: str
    price: int
    duration_min: int
    appointment_date: str
    start_time: str
    end_time: str
    status: str
    comment: str | None
    username: str | None = None
    full_name: str | None = None
    created_at: datetime | None = None

```

# ===== database/db.py =====
```python
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from config import DB_PATH, DEFAULT_SERVICES


class Database:
    async def _conn_fetchone(self, conn: aiosqlite.Connection, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        cursor = await conn.execute(sql, params)
        try:
            return await cursor.fetchone()
        finally:
            await cursor.close()

    def __init__(self, path: str = DB_PATH) -> None:
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self._tx_lock = asyncio.Lock()

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.execute("PRAGMA journal_mode = WAL")
        await self.conn.execute("PRAGMA busy_timeout = 5000")
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if self.conn is None:
            raise RuntimeError("База данных не подключена")
        return self.conn

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Cursor:
        conn = self._require_conn()
        return await conn.execute(sql, params)

    async def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> None:
        conn = self._require_conn()
        await conn.executemany(sql, params)

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        cursor = await self.execute(sql, params)
        try:
            return await cursor.fetchone()
        finally:
            await cursor.close()

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        cursor = await self.execute(sql, params)
        try:
            return await cursor.fetchall()
        finally:
            await cursor.close()

    async def commit(self) -> None:
        await self._require_conn().commit()

    async def rollback(self) -> None:
        await self._require_conn().rollback()

    @asynccontextmanager
    async def transaction(self, immediate: bool = False):
        """Transaction + mutex. Needed for booking/rescheduling race protection."""
        conn = self._require_conn()
        async with self._tx_lock:
            try:
                await conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def init_schema(self) -> None:
        conn = self._require_conn()
        schema = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL CHECK(price >= 0),
            duration_min INTEGER NOT NULL CHECK(duration_min > 0),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            appointment_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmed',
            comment TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            remind_24_sent INTEGER NOT NULL DEFAULT 0,
            remind_2_sent INTEGER NOT NULL DEFAULT 0,
            review_requested INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS blocked_times (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS waiting_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            preferred_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notified_at TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            text TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS blacklist (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_appointment_same_start
            ON appointments(appointment_date, start_time)
            WHERE status = 'confirmed';

        CREATE INDEX IF NOT EXISTS idx_appointments_date_status
            ON appointments(appointment_date, status);

        CREATE INDEX IF NOT EXISTS idx_waiting_list_lookup
            ON waiting_list(preferred_date, service_id, status);
        """
        await conn.executescript(schema)
        await conn.commit()

        row = await self.fetchone("SELECT COUNT(*) AS cnt FROM services")
        if row and row["cnt"] == 0:
            await self.executemany(
                "INSERT INTO services(name, price, duration_min, sort_order) VALUES (?, ?, ?, ?)",
                [(name, price, duration, idx) for idx, (name, price, duration) in enumerate(DEFAULT_SERVICES)],
            )
            await conn.commit()

    # ---------- users ----------
    async def upsert_user(self, user_id: int, username: str | None, full_name: str) -> None:
        await self.execute(
            """
            INSERT INTO users(id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, username, full_name),
        )
        await self.commit()

    async def is_blacklisted(self, user_id: int) -> bool:
        row = await self.fetchone("SELECT 1 FROM blacklist WHERE user_id = ?", (user_id,))
        return row is not None

    # ---------- services ----------
    async def get_active_services(self) -> list[aiosqlite.Row]:
        return await self.fetchall(
            "SELECT * FROM services WHERE is_active = 1 ORDER BY sort_order, id"
        )

    async def get_all_services(self) -> list[aiosqlite.Row]:
        return await self.fetchall("SELECT * FROM services ORDER BY sort_order, id")

    async def get_service(self, service_id: int) -> aiosqlite.Row | None:
        return await self.fetchone("SELECT * FROM services WHERE id = ?", (service_id,))

    async def update_service_field(self, service_id: int, field: str, value: Any) -> None:
        if field not in {"name", "price", "duration_min"}:
            raise ValueError("Недопустимое поле услуги")
        await self.execute(f"UPDATE services SET {field} = ? WHERE id = ?", (value, service_id))
        await self.commit()

    async def toggle_service(self, service_id: int) -> None:
        await self.execute(
            "UPDATE services SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id = ?",
            (service_id,),
        )
        await self.commit()

    async def add_service(self, name: str, price: int, duration_min: int) -> int:
        cursor = await self.execute(
            "INSERT INTO services(name, price, duration_min, sort_order) VALUES (?, ?, ?, ?)",
            (name, price, duration_min, 999),
        )
        await self.commit()
        return int(cursor.lastrowid)

    # ---------- appointments ----------
    async def get_appointments_for_date(self, date_iso: str, only_confirmed: bool = True) -> list[aiosqlite.Row]:
        where_status = "AND a.status = 'confirmed'" if only_confirmed else ""
        return await self.fetchall(
            f"""
            SELECT a.*, s.name AS service_name, s.price, s.duration_min,
                   u.username, u.full_name
            FROM appointments a
            JOIN services s ON s.id = a.service_id
            JOIN users u ON u.id = a.user_id
            WHERE a.appointment_date = ? {where_status}
            ORDER BY a.start_time
            """,
            (date_iso,),
        )

    async def get_appointments_for_user(self, user_id: int, from_iso: str) -> list[aiosqlite.Row]:
        return await self.fetchall(
            """
            SELECT a.*, s.name AS service_name, s.price, s.duration_min
            FROM appointments a
            JOIN services s ON s.id = a.service_id
            WHERE a.user_id = ?
              AND a.status = 'confirmed'
              AND (a.appointment_date > ? OR (a.appointment_date = ? AND a.start_time >= ?))
            ORDER BY a.appointment_date, a.start_time
            """,
            (user_id, from_iso[:10], from_iso[:10], from_iso[11:16]),
        )

    async def get_appointment(self, appointment_id: int) -> aiosqlite.Row | None:
        return await self.fetchone(
            """
            SELECT a.*, s.name AS service_name, s.price, s.duration_min,
                   u.username, u.full_name
            FROM appointments a
            JOIN services s ON s.id = a.service_id
            JOIN users u ON u.id = a.user_id
            WHERE a.id = ?
            """,
            (appointment_id,),
        )

    async def create_appointment(
        self,
        user_id: int,
        service_id: int,
        date_iso: str,
        start_time: str,
        end_time: str,
        comment: str | None,
    ) -> tuple[bool, int | None, str | None]:
        """Returns (success, appointment_id, error_code)."""
        async with self.transaction(immediate=True) as conn:
            user = await self._conn_fetchone(conn, "SELECT 1 FROM users WHERE id = ?", (user_id,))
            if user is None:
                raise RuntimeError("Пользователь не найден")
            service = await self._conn_fetchone(
                conn, "SELECT * FROM services WHERE id = ? AND is_active = 1", (service_id,)
            )
            if service is None:
                return False, None, "service_unavailable"
            blacklisted = await self._conn_fetchone(
                conn, "SELECT 1 FROM blacklist WHERE user_id = ?", (user_id,)
            )
            if blacklisted is not None:
                return False, None, "blacklisted"

            # Check any overlap, including the mandatory buffer.
            existing = await conn.execute_fetchall(
                """
                SELECT a.start_time, a.end_time
                FROM appointments a
                WHERE a.appointment_date = ? AND a.status = 'confirmed'
                """,
                (date_iso,),
            )
            blocked = await conn.execute_fetchall(
                "SELECT start_time, end_time FROM blocked_times WHERE block_date = ?",
                (date_iso,),
            )
            if _overlaps_for_booking(start_time, end_time, existing, blocked):
                return False, None, "slot_taken"

            try:
                cursor = await conn.execute(
                    """
                    INSERT INTO appointments(user_id, service_id, appointment_date, start_time, end_time, comment)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, service_id, date_iso, start_time, end_time, comment),
                )
            except aiosqlite.IntegrityError:
                return False, None, "slot_taken"
            return True, int(cursor.lastrowid), None

    async def cancel_appointment(self, appointment_id: int, user_id: int | None = None) -> bool:
        async with self.transaction(immediate=True) as conn:
            where = "WHERE id = ? AND status = 'confirmed'"
            params: tuple[Any, ...] = (appointment_id,)
            if user_id is not None:
                where += " AND user_id = ?"
                params += (user_id,)
            cursor = await conn.execute(
                f"UPDATE appointments SET status='cancelled', updated_at=CURRENT_TIMESTAMP {where}",
                params,
            )
            return cursor.rowcount > 0

    async def reschedule_appointment(
        self,
        appointment_id: int,
        user_id: int,
        new_date: str,
        new_start: str,
        new_end: str,
    ) -> tuple[bool, str | None]:
        async with self.transaction(immediate=True) as conn:
            appointment = await self._conn_fetchone(
                conn,
                "SELECT * FROM appointments WHERE id = ? AND user_id = ? AND status = 'confirmed'",
                (appointment_id, user_id),
            )
            if appointment is None:
                return False, "not_found"

            existing = await conn.execute_fetchall(
                """
                SELECT start_time, end_time FROM appointments
                WHERE appointment_date = ? AND status='confirmed' AND id != ?
                """,
                (new_date, appointment_id),
            )
            blocked = await conn.execute_fetchall(
                "SELECT start_time, end_time FROM blocked_times WHERE block_date = ?",
                (new_date,),
            )
            if _overlaps_for_booking(new_start, new_end, existing, blocked):
                return False, "slot_taken"

            try:
                await conn.execute(
                    """
                    UPDATE appointments
                    SET appointment_date=?, start_time=?, end_time=?,
                        updated_at=CURRENT_TIMESTAMP, remind_24_sent=0, remind_2_sent=0, review_requested=0
                    WHERE id=?
                    """,
                    (new_date, new_start, new_end, appointment_id),
                )
            except aiosqlite.IntegrityError:
                return False, "slot_taken"
            return True, None

    async def reset_reminders_if_needed(self, appointment_id: int) -> None:
        await self.execute(
            "UPDATE appointments SET remind_24_sent=0, remind_2_sent=0 WHERE id = ?",
            (appointment_id,),
        )
        await self.commit()

    async def get_upcoming_for_reminders(self) -> list[aiosqlite.Row]:
        return await self.fetchall(
            """
            SELECT a.*, s.name AS service_name, u.username, u.full_name
            FROM appointments a
            JOIN services s ON s.id = a.service_id
            JOIN users u ON u.id = a.user_id
            WHERE a.status='confirmed'
            """
        )

    async def mark_reminder_sent(self, appointment_id: int, kind: str) -> None:
        column = "remind_24_sent" if kind == "24" else "remind_2_sent"
        await self.execute(f"UPDATE appointments SET {column}=1 WHERE id=?", (appointment_id,))
        await self.commit()

    async def mark_review_requested(self, appointment_id: int) -> None:
        await self.execute("UPDATE appointments SET review_requested=1 WHERE id=?", (appointment_id,))
        await self.commit()

    async def get_completed_without_review(self) -> list[aiosqlite.Row]:
        return await self.fetchall(
            """
            SELECT a.*, s.name AS service_name
            FROM appointments a
            JOIN services s ON s.id=a.service_id
            LEFT JOIN reviews r ON r.appointment_id=a.id
            WHERE a.status='confirmed'
              AND r.id IS NULL
              AND a.review_requested=0
            """
        )

    # ---------- blocked times ----------
    async def add_blocked_time(self, date_iso: str, start: str, end: str, reason: str | None) -> int:
        cursor = await self.execute(
            "INSERT INTO blocked_times(block_date,start_time,end_time,reason) VALUES (?,?,?,?)",
            (date_iso, start, end, reason),
        )
        await self.commit()
        return int(cursor.lastrowid)

    async def get_blocked_between(self, from_date: str, to_date: str) -> list[aiosqlite.Row]:
        return await self.fetchall(
            """
            SELECT * FROM blocked_times
            WHERE block_date BETWEEN ? AND ?
            ORDER BY block_date, start_time
            """,
            (from_date, to_date),
        )

    async def delete_blocked_time(self, block_id: int) -> tuple[bool, str | None]:
        row = await self.fetchone("SELECT block_date FROM blocked_times WHERE id=?", (block_id,))
        if row is None:
            return False, None
        await self.execute("DELETE FROM blocked_times WHERE id=?", (block_id,))
        await self.commit()
        return True, row["block_date"]

    # ---------- waiting list ----------
    async def add_waiting(self, user_id: int, service_id: int, preferred_date: str) -> bool:
        if await self.is_blacklisted(user_id):
            return False
        existing = await self.fetchone(
            """
            SELECT 1 FROM waiting_list
            WHERE user_id=? AND service_id=? AND preferred_date=? AND status='active'
            """,
            (user_id, service_id, preferred_date),
        )
        if existing:
            return False
        await self.execute(
            "INSERT INTO waiting_list(user_id,service_id,preferred_date) VALUES (?,?,?)",
            (user_id, service_id, preferred_date),
        )
        await self.commit()
        return True

    async def get_active_waiting_for_date(self, date_iso: str) -> list[aiosqlite.Row]:
        return await self.fetchall(
            """
            SELECT w.*, s.name AS service_name, s.price, s.duration_min, u.username, u.full_name
            FROM waiting_list w
            JOIN services s ON s.id=w.service_id
            JOIN users u ON u.id=w.user_id
            WHERE w.preferred_date=? AND w.status='active'
            ORDER BY w.created_at
            """,
            (date_iso,),
        )

    async def mark_waiting_notified(self, waiting_id: int) -> None:
        await self.execute(
            "UPDATE waiting_list SET status='notified', notified_at=CURRENT_TIMESTAMP WHERE id=?",
            (waiting_id,),
        )
        await self.commit()

    async def get_waiting_for_user(self, user_id: int) -> list[aiosqlite.Row]:
        return await self.fetchall(
            """
            SELECT w.*, s.name AS service_name
            FROM waiting_list w JOIN services s ON s.id=w.service_id
            WHERE w.user_id=? AND w.status='active'
            ORDER BY w.preferred_date, w.created_at
            """,
            (user_id,),
        )

    # ---------- reviews ----------
    async def add_review(self, appointment_id: int, user_id: int, rating: int, text: str | None) -> bool:
        appointment = await self.fetchone(
            "SELECT id FROM appointments WHERE id=? AND user_id=? AND status='confirmed'",
            (appointment_id, user_id),
        )
        if appointment is None:
            return False
        try:
            await self.execute(
                "INSERT INTO reviews(appointment_id,user_id,rating,text) VALUES (?,?,?,?)",
                (appointment_id, user_id, rating, text),
            )
            await self.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def get_reviews(self, limit: int = 20) -> list[aiosqlite.Row]:
        return await self.fetchall(
            """
            SELECT r.*, u.full_name, u.username, a.appointment_date, a.start_time, s.name AS service_name
            FROM reviews r
            JOIN users u ON u.id=r.user_id
            JOIN appointments a ON a.id=r.appointment_id
            JOIN services s ON s.id=a.service_id
            ORDER BY r.created_at DESC LIMIT ?
            """,
            (limit,),
        )

    # ---------- blacklist ----------
    async def add_blacklist(self, user_id: int, reason: str | None) -> None:
        await self.execute(
            "INSERT OR REPLACE INTO blacklist(user_id, reason) VALUES (?, ?)",
            (user_id, reason),
        )
        await self.commit()

    async def remove_blacklist(self, user_id: int) -> None:
        await self.execute("DELETE FROM blacklist WHERE user_id=?", (user_id,))
        await self.commit()

    async def get_blacklist(self) -> list[aiosqlite.Row]:
        return await self.fetchall(
            """
            SELECT b.*, u.full_name, u.username
            FROM blacklist b LEFT JOIN users u ON u.id=b.user_id
            ORDER BY b.created_at DESC
            """
        )

    # ---------- stats ----------
    async def get_stats(self) -> dict[str, Any]:
        users = await self.fetchone("SELECT COUNT(*) AS cnt FROM users")
        total = await self.fetchone("SELECT COUNT(*) AS cnt FROM appointments")
        confirmed = await self.fetchone("SELECT COUNT(*) AS cnt FROM appointments WHERE status='confirmed'")
        cancelled = await self.fetchone("SELECT COUNT(*) AS cnt FROM appointments WHERE status='cancelled'")
        from services.booking import now_local
        now = now_local()
        today = now.date().isoformat()
        current_time = now.strftime("%H:%M")
        future_confirmed = await self.fetchone(
            """
            SELECT COUNT(*) AS cnt FROM appointments
            WHERE status='confirmed'
              AND (appointment_date > ? OR (appointment_date = ? AND start_time >= ?))
            """,
            (today, today, current_time),
        )
        revenue = await self.fetchone(
            """
            SELECT COALESCE(SUM(s.price),0) AS total
            FROM appointments a JOIN services s ON s.id=a.service_id
            WHERE a.status='confirmed'
              AND (a.appointment_date < ? OR (a.appointment_date = ? AND a.end_time <= ?))
            """,
            (today, today, current_time),
        )
        rating = await self.fetchone("SELECT ROUND(AVG(rating),2) AS avg_rating, COUNT(*) AS cnt FROM reviews")
        blacklisted = await self.fetchone("SELECT COUNT(*) AS cnt FROM blacklist")
        return {
            "users": users["cnt"],
            "appointments": total["cnt"],
            "confirmed": confirmed["cnt"],
            "future_confirmed": future_confirmed["cnt"],
            "cancelled": cancelled["cnt"],
            "revenue": revenue["total"],
            "avg_rating": rating["avg_rating"] if rating else None,
            "review_count": rating["cnt"] if rating else 0,
            "blacklisted": blacklisted["cnt"],
        }


def _to_minutes(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and a_end > b_start


def _overlaps_for_booking(start_time: str, end_time: str, existing, blocked) -> bool:
    start = _to_minutes(start_time)
    end = _to_minutes(end_time)
    # Buffer is applied to each appointment interval by checking a 15-minute expansion.
    from config import BUFFER_MINUTES

    for row in existing:
        e_start = _to_minutes(row["start_time"])
        e_end = _to_minutes(row["end_time"])
        if _overlap(start - BUFFER_MINUTES, end + BUFFER_MINUTES, e_start, e_end):
            return True
    for row in blocked:
        b_start = _to_minutes(row["start_time"])
        b_end = _to_minutes(row["end_time"])
        if _overlap(start, end, b_start, b_end):
            return True
    return False

```

# ===== handlers/__init__.py =====
```python

```

# ===== handlers/common.py =====
```python
import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID, MASTER_NAME
from database.db import Database
from keyboards.admin_kb import admin_menu
from keyboards.user_kb import main_menu

router = Router(name="common")
logger = logging.getLogger(__name__)


async def ensure_user(message: Message, db: Database) -> None:
    user = message.from_user
    if user is None:
        return
    full_name = " ".join(x for x in [user.first_name, user.last_name] if x).strip() or "Без имени"
    await db.upsert_user(user.id, user.username, full_name)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await ensure_user(message, db)
    restricted = await db.is_blacklisted(message.from_user.id)
    text = f"💅 <b>{MASTER_NAME}</b>\n\nДобро пожаловать! Выберите действие в меню."
    if restricted:
        text += "\n\n⚠️ Для вашего аккаунта ограничена возможность новых записей."
    await message.answer(text, reply_markup=main_menu())


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await ensure_user(message, db)
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_menu())

```

# ===== handlers/user.py =====
```python
import html
import logging
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from config import CANCELLATION_CUTOFF_HOURS, CONTACTS_TEXT, MASTER_NAME, TIMEZONE
from database.db import Database
from keyboards.user_kb import (
    appointment_actions_keyboard,
    appointments_keyboard,
    booking_confirm_keyboard,
    date_keyboard,
    main_menu,
    no_slots_keyboard,
    rating_keyboard,
    reschedule_confirm_keyboard,
    services_keyboard,
    skip_comment_keyboard,
    skip_review_text_keyboard,
    time_keyboard,
    waiting_list_keyboard,
    waiting_services_keyboard,
)
from services.booking import (
    fmt_price,
    get_available_slots,
    get_end_time,
    is_cancel_allowed,
    next_working_days,
    now_local,
    ru_date,
)
from states.states import BookingState, RescheduleState, ReviewState, WaitingState

router = Router(name="user")
logger = logging.getLogger(__name__)


async def blocked_guard(user_id: int, db: Database) -> bool:
    return await db.is_blacklisted(user_id)


async def show_booking_dates(message_or_callback, state: FSMContext, db: Database, service_id: int) -> None:
    dates = []
    for d in next_working_days():
        slots = await get_available_slots(db, service_id, d.isoformat())
        label = f"{ru_date(d.isoformat())} · {len(slots)}"
        dates.append((d.isoformat(), label))
    await state.update_data(service_id=service_id)
    await state.set_state(BookingState.date)
    text = "📅 <b>Выберите дату</b>\n\nЧисло справа — количество свободных вариантов времени."
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(text, reply_markup=date_keyboard(dates))
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text, reply_markup=date_keyboard(dates))


async def show_reschedule_dates(callback: CallbackQuery, state: FSMContext, db: Database, service_id: int) -> None:
    dates = []
    for d in next_working_days():
        slots = await get_available_slots(db, service_id, d.isoformat())
        label = f"{ru_date(d.isoformat())} · {len(slots)}"
        dates.append((d.isoformat(), label))
    await state.update_data(service_id=service_id)
    await state.set_state(RescheduleState.date)
    await callback.message.edit_text("📅 <b>Выберите новую дату</b>", reply_markup=date_keyboard(dates, prefix="reschedule_date"))
    await callback.answer()


@router.message(F.text == "📝 Записаться")
async def booking_start(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    if await blocked_guard(message.from_user.id, db):
        await message.answer("⚠️ Новая запись для этого аккаунта недоступна.", reply_markup=main_menu())
        return
    services = await db.get_active_services()
    await state.set_state(BookingState.service)
    await message.answer("💅 <b>Выберите услугу</b>", reply_markup=services_keyboard(services))


@router.callback_query(F.data == "user_menu")
async def user_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("🏠 Главное меню", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(BookingState.service, F.data.startswith("book_service:"))
async def booking_service(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    service_id = int(callback.data.split(":", 1)[1])
    service = await db.get_service(service_id)
    if service is None or not service["is_active"]:
        await callback.answer("Эта услуга сейчас недоступна", show_alert=True)
        return
    await show_booking_dates(callback, state, db, service_id)


@router.callback_query(BookingState.date, F.data.startswith("book_date:"))
async def booking_date(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    _, date_iso = callback.data.split(":", 1)
    data = await state.get_data()
    service_id = int(data["service_id"])
    slots = await get_available_slots(db, service_id, date_iso)
    await state.update_data(date_iso=date_iso)
    await state.set_state(BookingState.time)
    if slots:
        await callback.message.edit_text(
            f"🕐 <b>Выберите время</b>\n{ru_date(date_iso)}",
            reply_markup=time_keyboard(date_iso, service_id, slots),
        )
    else:
        await callback.message.edit_text(
            f"😔 На {ru_date(date_iso)} свободного времени нет.",
            reply_markup=no_slots_keyboard(date_iso, service_id),
        )
    await callback.answer()


@router.callback_query(F.data == "book_back_dates")
async def booking_back_dates(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    service_id = data.get("service_id")
    if not service_id:
        await state.clear()
        await callback.message.answer("🏠 Главное меню", reply_markup=main_menu())
        await callback.answer()
        return
    await show_booking_dates(callback, state, db, int(service_id))


@router.callback_query(F.data.startswith("book_time|"))
async def booking_time(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    try:
        _, date_iso, service_id_raw, start_raw = callback.data.split("|")
        start_time = f"{start_raw[:2]}:{start_raw[2:]}"
        service_id = int(service_id_raw)
    except ValueError:
        await callback.answer("Некорректное время", show_alert=True)
        return
    if await blocked_guard(callback.from_user.id, db):
        await callback.answer("Доступ к записи ограничен", show_alert=True)
        return
    slots = await get_available_slots(db, service_id, date_iso)
    if start_time not in slots:
        await callback.answer("Это время уже заняли. Выберите другое.", show_alert=True)
        await state.set_state(BookingState.time)
        await callback.message.edit_text(
            f"🕐 <b>Выберите другое время</b>\n{ru_date(date_iso)}",
            reply_markup=time_keyboard(date_iso, service_id, slots) if slots else no_slots_keyboard(date_iso, service_id),
        )
        return
    service = await db.get_service(service_id)
    await state.update_data(service_id=service_id, date_iso=date_iso, start_time=start_time)
    await state.set_state(BookingState.comment)
    await callback.message.edit_text(
        f"📝 <b>Пожелания к записи</b>\n\n"
        f"Услуга: {service['name']}\n"
        f"Дата: {ru_date(date_iso)}\n"
        f"Время: <b>{start_time}</b>\n\n"
        "Напишите комментарий или нажмите «Пропустить».",
        reply_markup=skip_comment_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wait_time|"))
async def waitlist_choose_time(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    try:
        _, date_iso, service_id_raw, start_raw = callback.data.split("|")
        start_time = f"{start_raw[:2]}:{start_raw[2:]}"
        service_id = int(service_id_raw)
    except ValueError:
        await callback.answer("Некорректное время", show_alert=True)
        return
    slots = await get_available_slots(db, service_id, date_iso)
    if start_time not in slots:
        await callback.answer("Это время уже недоступно.", show_alert=True)
        return
    await state.clear()
    await state.update_data(service_id=service_id, date_iso=date_iso, start_time=start_time)
    await state.set_state(BookingState.comment)
    service = await db.get_service(service_id)
    await callback.message.edit_text(
        f"📝 <b>Пожелания к записи</b>\n\n{service['name']}\n{ru_date(date_iso)} · <b>{start_time}</b>\n\nНапишите комментарий или пропустите.",
        reply_markup=skip_comment_keyboard(),
    )
    await callback.answer("Время доступно — можно записываться")


@router.message(BookingState.comment)
async def booking_comment(message: Message, state: FSMContext, db: Database) -> None:
    comment = (message.text or "").strip()
    if len(comment) > 1000:
        await message.answer("Комментарий слишком длинный. Максимум 1000 символов.")
        return
    await state.update_data(comment=comment or None)
    await show_booking_confirmation(message, state, db)


@router.callback_query(BookingState.comment, F.data == "skip_comment")
async def booking_skip_comment(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.update_data(comment=None)
    await show_booking_confirmation(callback.message, state, db, edit=True)
    await callback.answer()


async def show_booking_confirmation(message: Message, state: FSMContext, db: Database, edit: bool = False) -> None:
    data = await state.get_data()
    service = await db.get_service(int(data["service_id"]))
    text = (
        "✅ <b>Проверьте запись</b>\n\n"
        f"💅 {service['name']}\n"
        f"📅 {ru_date(data['date_iso'])}\n"
        f"🕐 {data['start_time']}–{get_end_time(data['start_time'], int(service['duration_min']))}\n"
        f"💰 {fmt_price(int(service['price']))}\n"
        f"📝 Пожелания: {html.escape(data.get('comment') or '—')}\n\n"
        "Подтвердить запись?"
    )
    await state.set_state(BookingState.confirm)
    if edit:
        await message.edit_text(text, reply_markup=booking_confirm_keyboard())
    else:
        await message.answer(text, reply_markup=booking_confirm_keyboard())


@router.callback_query(BookingState.confirm, F.data == "book_confirm")
async def booking_confirm(callback: CallbackQuery, state: FSMContext, db: Database, bot) -> None:
    if await blocked_guard(callback.from_user.id, db):
        await state.clear()
        await callback.answer("Доступ к записи ограничен", show_alert=True)
        return
    data = await state.get_data()
    service = await db.get_service(int(data["service_id"]))
    end_time = get_end_time(data["start_time"], int(service["duration_min"]))
    success, appointment_id, error = await db.create_appointment(
        callback.from_user.id,
        int(data["service_id"]),
        data["date_iso"],
        data["start_time"],
        end_time,
        data.get("comment"),
    )
    if not success:
        if error == "slot_taken":
            await callback.answer("Это время уже заняли. Выберите другое.", show_alert=True)
        else:
            await callback.answer("Не удалось создать запись.", show_alert=True)
        await state.set_state(BookingState.time)
        slots = await get_available_slots(db, int(data["service_id"]), data["date_iso"])
        await callback.message.edit_text(
            "🕐 <b>Выберите другое время</b>",
            reply_markup=time_keyboard(data["date_iso"], int(data["service_id"]), slots)
            if slots else no_slots_keyboard(data["date_iso"], int(data["service_id"])),
        )
        return

    await state.clear()
    await callback.message.answer(
        "🎉 <b>Запись подтверждена!</b>\n\n"
        f"{service['name']}\n{ru_date(data['date_iso'])} · <b>{data['start_time']}</b>\n"
        f"Стоимость: {fmt_price(int(service['price']))}\n\n"
        "Я напомню вам о визите за 24 часа и за 2 часа.",
        reply_markup=main_menu(),
    )
    await callback.answer("Запись создана")
    user = callback.from_user
    username = f"@{user.username}" if user.username else "без username"
    await bot.send_message(
        ADMIN_ID,
        "🆕 <b>Новая запись</b>\n\n"
        f"Клиент: {html.escape(user.full_name)} ({username})\n"
        f"Услуга: {service['name']}\n"
        f"Дата: {ru_date(data['date_iso'])}\n"
        f"Время: <b>{data['start_time']}</b>\n"
        f"Комментарий: {html.escape(data.get('comment') or '—')}\n"
        f"ID записи: <code>{appointment_id}</code>",
    )


@router.message(F.text == "📅 Мои записи")
async def my_appointments(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    now = now_local().strftime("%Y-%m-%dT%H:%M")
    rows = await db.get_appointments_for_user(message.from_user.id, now)
    if not rows:
        await message.answer("📭 Будущих записей нет.", reply_markup=main_menu())
        return
    parts = ["📅 <b>Мои записи</b>"]
    for row in rows:
        parts.append(
            f"\n💅 {row['service_name']}\n"
            f"📅 {ru_date(row['appointment_date'])}\n"
            f"🕐 <b>{row['start_time']}</b>–{row['end_time']}\n"
            f"💰 {fmt_price(int(row['price']))}"
        )
    await message.answer("\n".join(parts), reply_markup=appointments_keyboard(rows))


@router.callback_query(F.data == "my_appointments")
async def my_appointments_callback(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    now = now_local().strftime("%Y-%m-%dT%H:%M")
    rows = await db.get_appointments_for_user(callback.from_user.id, now)
    if not rows:
        await callback.message.edit_text("📭 Будущих записей нет.")
        await callback.answer()
        return
    await callback.message.edit_text("📅 <b>Выберите запись</b>", reply_markup=appointments_keyboard(rows))
    await callback.answer()


@router.callback_query(F.data.startswith("manage_appt:"))
async def manage_appointment(callback: CallbackQuery, db: Database) -> None:
    appointment_id = int(callback.data.split(":", 1)[1])
    row = await db.get_appointment(appointment_id)
    if row is None or row["user_id"] != callback.from_user.id or row["status"] != "confirmed":
        await callback.answer("Запись не найдена", show_alert=True)
        return
    text = (
        "📌 <b>Запись</b>\n\n"
        f"💅 {row['service_name']}\n📅 {ru_date(row['appointment_date'])}\n"
        f"🕐 {row['start_time']}–{row['end_time']}\n💰 {fmt_price(int(row['price']))}\n"
        f"📝 {html.escape(row['comment'] or '—')}"
    )
    await callback.message.edit_text(text, reply_markup=appointment_actions_keyboard(appointment_id))
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_appt:"))
async def cancel_appointment(callback: CallbackQuery, db: Database, bot) -> None:
    appointment_id = int(callback.data.split(":", 1)[1])
    row = await db.get_appointment(appointment_id)
    if row is None or row["user_id"] != callback.from_user.id or row["status"] != "confirmed":
        await callback.answer("Запись не найдена", show_alert=True)
        return
    if not is_cancel_allowed(row["appointment_date"], row["start_time"]):
        await callback.answer("Отменить или перенести запись можно не позднее чем за 3 часа.", show_alert=True)
        return
    if not await db.cancel_appointment(appointment_id, callback.from_user.id):
        await callback.answer("Запись уже изменена.", show_alert=True)
        return
    await callback.message.edit_text("✅ Запись отменена.")
    await callback.message.answer("🏠 Главное меню", reply_markup=main_menu())
    await callback.answer("Отменено")
    await bot.send_message(
        ADMIN_ID,
        "❌ <b>Запись отменена</b>\n\n"
        f"Клиент: {html.escape(callback.from_user.full_name)}\n"
        f"Услуга: {row['service_name']}\n"
        f"Дата: {ru_date(row['appointment_date'])}\nВремя: {row['start_time']}\n"
        f"ID записи: <code>{appointment_id}</code>",
    )
    from services.waitlist import notify_waiting_list_for_date
    await notify_waiting_list_for_date(bot, db, row["appointment_date"])


@router.message(F.text == "❌ Отменить / Перенести запись")
async def manage_appointments_menu(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await my_appointments(message, state, db)


@router.callback_query(F.data.startswith("reschedule_start:"))
async def reschedule_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    appointment_id = int(callback.data.split(":", 1)[1])
    row = await db.get_appointment(appointment_id)
    if row is None or row["user_id"] != callback.from_user.id or row["status"] != "confirmed":
        await callback.answer("Запись не найдена", show_alert=True)
        return
    if not is_cancel_allowed(row["appointment_date"], row["start_time"]):
        await callback.answer("Перенести можно не позднее чем за 3 часа.", show_alert=True)
        return
    await state.clear()
    await state.update_data(appointment_id=appointment_id, service_id=int(row["service_id"]))
    await show_reschedule_dates(callback, state, db, int(row["service_id"]))


@router.callback_query(F.data.startswith("reschedule_date:"))
async def reschedule_date(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    date_iso = callback.data.split(":", 1)[1]
    data = await state.get_data()
    service_id = int(data["service_id"])
    slots = await get_available_slots(db, service_id, date_iso)
    await state.update_data(new_date_iso=date_iso)
    await state.set_state(RescheduleState.time)
    if not slots:
        await callback.message.edit_text("😔 На эту дату свободного времени нет.", reply_markup=date_keyboard([(d.isoformat(), ru_date(d.isoformat())) for d in next_working_days()], prefix="reschedule_date"))
    else:
        # Reuse time keyboard semantics but a different callback prefix.
        builder = InlineKeyboardBuilder()
        for slot in slots:
            builder.button(text=slot, callback_data=f"reschedule_time|{date_iso}|{service_id}|{slot.replace(':', '')}")
        builder.adjust(3)
        builder.row(InlineKeyboardButton(text="⬅️ К датам", callback_data=f"reschedule_back_dates"))
        await callback.message.edit_text(
            f"🕐 <b>Новое время</b> — {ru_date(date_iso)}",
            reply_markup=builder.as_markup(),
        )
    await callback.answer()


@router.callback_query(F.data == "reschedule_back_dates")
async def reschedule_back_dates(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    await show_reschedule_dates(callback, state, db, int(data["service_id"]))


@router.callback_query(F.data.startswith("reschedule_time|"))
async def reschedule_time(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    _, date_iso, service_id_raw, start_raw = callback.data.split("|")
    start_time = f"{start_raw[:2]}:{start_raw[2:]}"
    service_id = int(service_id_raw)
    slots = await get_available_slots(db, service_id, date_iso)
    if start_time not in slots:
        await callback.answer("Это время уже заняли.", show_alert=True)
        return
    data = await state.get_data()
    appointment = await db.get_appointment(int(data["appointment_id"]))
    if appointment is None:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    end_time = get_end_time(start_time, int(appointment["duration_min"]))
    await state.update_data(new_date_iso=date_iso, new_start_time=start_time, new_end_time=end_time)
    await state.set_state(RescheduleState.confirm)
    await callback.message.edit_text(
        "🔄 <b>Подтвердите перенос</b>\n\n"
        f"Было: {ru_date(appointment['appointment_date'])} · {appointment['start_time']}\n"
        f"Станет: {ru_date(date_iso)} · <b>{start_time}</b>\n"
        f"Услуга: {appointment['service_name']}",
        reply_markup=reschedule_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(RescheduleState.confirm, F.data == "reschedule_confirm")
async def reschedule_confirm(callback: CallbackQuery, state: FSMContext, db: Database, bot) -> None:
    data = await state.get_data()
    old = await db.get_appointment(int(data["appointment_id"]))
    if old is None or not is_cancel_allowed(old["appointment_date"], old["start_time"]):
        await state.clear()
        await callback.answer("Перенос больше недоступен.", show_alert=True)
        return
    ok, error = await db.reschedule_appointment(
        int(data["appointment_id"]),
        callback.from_user.id,
        data["new_date_iso"],
        data["new_start_time"],
        data["new_end_time"],
    )
    if not ok:
        await callback.answer("Новое время уже занято.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Запись перенесена</b>\n\n"
        f"Новая дата: {ru_date(data['new_date_iso'])}\n"
        f"Новое время: <b>{data['new_start_time']}</b>"
    )
    await callback.message.answer("🏠 Главное меню", reply_markup=main_menu())
    await callback.answer("Перенесено")
    await bot.send_message(
        ADMIN_ID,
        "🔄 <b>Перенос записи</b>\n\n"
        f"Клиент: {html.escape(callback.from_user.full_name)}\n"
        f"Услуга: {old['service_name']}\n"
        f"Было: {ru_date(old['appointment_date'])} · {old['start_time']}\n"
        f"Стало: {ru_date(data['new_date_iso'])} · {data['new_start_time']}\n"
        f"ID записи: <code>{data['appointment_id']}</code>",
    )
    from services.waitlist import notify_waiting_list_for_date
    await notify_waiting_list_for_date(bot, db, old["appointment_date"])


@router.message(F.text == "💰 Услуги и цены")
async def show_services(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    services = await db.get_active_services()
    lines = ["💰 <b>Услуги и цены</b>"]
    for s in services:
        lines.append(f"\n💅 <b>{s['name']}</b>\n{fmt_price(int(s['price']))} · {s['duration_min']} мин")
    await message.answer("\n".join(lines), reply_markup=main_menu())


@router.message(F.text == "📍 Контакты")
async def contacts(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(f"📍 <b>{MASTER_NAME}</b>\n\n{CONTACTS_TEXT}", reply_markup=main_menu())


@router.message(F.text == "⏳ Лист ожидания")
async def waiting_start(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    if await blocked_guard(message.from_user.id, db):
        await message.answer("⚠️ Лист ожидания для этого аккаунта недоступен.", reply_markup=main_menu())
        return
    services = await db.get_active_services()
    active = await db.get_waiting_for_user(message.from_user.id)
    text = "⏳ <b>Лист ожидания</b>\n\nВыберите услугу и желаемую дату."
    if active:
        text += "\n\n<b>Ваши активные заявки:</b>\n" + "\n".join(
            f"• {x['preferred_date']} — {x['service_name']}" for x in active
        )
    await state.set_state(WaitingState.service)
    await message.answer(text, reply_markup=waiting_services_keyboard(services, active))


@router.callback_query(WaitingState.service, F.data.startswith("wait_service:"))
async def waiting_service(callback: CallbackQuery, state: FSMContext) -> None:
    service_id = int(callback.data.split(":", 1)[1])
    await state.update_data(service_id=service_id)
    await state.set_state(WaitingState.date)
    dates = [(d.isoformat(), ru_date(d.isoformat())) for d in next_working_days()]
    await callback.message.edit_text("📅 <b>На какую дату поставить в лист ожидания?</b>", reply_markup=date_keyboard(dates, prefix="wait_date"))
    await callback.answer()


@router.callback_query(WaitingState.date, F.data.startswith("wait_date:"))
async def waiting_date(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    date_iso = callback.data.split(":", 1)[1]
    data = await state.get_data()
    service_id = int(data["service_id"])
    ok = await db.add_waiting(callback.from_user.id, service_id, date_iso)
    await state.clear()
    if ok:
        await callback.message.edit_text("✅ Вы добавлены в лист ожидания.\n\nЯ сообщу, когда появится свободное время.")
    else:
        await callback.message.edit_text("ℹ️ Такая заявка уже есть или добавить её не удалось.")
    await callback.message.answer("🏠 Главное меню", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("wait_add:"))
async def waiting_add_direct(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    _, date_iso, service_id_raw = callback.data.split(":")
    service_id = int(service_id_raw)
    if await blocked_guard(callback.from_user.id, db):
        await callback.answer("Доступ ограничен", show_alert=True)
        return
    ok = await db.add_waiting(callback.from_user.id, service_id, date_iso)
    await state.clear()
    await callback.answer("Вы добавлены в лист ожидания" if ok else "Такая заявка уже есть", show_alert=True)


@router.callback_query(F.data.startswith("wait_cancel:"))
async def waiting_cancel(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    waiting_id = int(callback.data.split(":", 1)[1])
    row = await db.fetchone(
        "SELECT id FROM waiting_list WHERE id=? AND user_id=? AND status='active'",
        (waiting_id, callback.from_user.id),
    )
    if row is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await db.execute("UPDATE waiting_list SET status='cancelled' WHERE id=?", (waiting_id,))
    await db.commit()
    active = await db.get_waiting_for_user(callback.from_user.id)
    await callback.answer("Заявка отменена")
    if active:
        text = "⏳ <b>Ваш лист ожидания</b>\n\n" + "\n".join(
            f"• {x['preferred_date']} — {x['service_name']}" for x in active
        )
        await callback.message.edit_text(text, reply_markup=waiting_list_keyboard(active))
    else:
        await callback.message.edit_text("⏳ Активных заявок в листе ожидания нет.")


@router.callback_query(F.data.startswith("review:"))
async def review_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    appointment_id = int(callback.data.split(":", 1)[1])
    row = await db.get_appointment(appointment_id)
    if row is None or row["user_id"] != callback.from_user.id or row["status"] != "confirmed":
        await callback.answer("Отзыв недоступен", show_alert=True)
        return
    await state.clear()
    await state.update_data(appointment_id=appointment_id)
    await state.set_state(ReviewState.rating)
    await callback.message.edit_text("⭐ <b>Оцените визит от 1 до 5</b>", reply_markup=rating_keyboard(appointment_id))
    await callback.answer()


@router.callback_query(ReviewState.rating, F.data.startswith("rating:"))
async def review_rating(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    _, appointment_id_raw, rating_raw = callback.data.split(":")
    appointment_id = int(appointment_id_raw)
    rating = int(rating_raw)
    row = await db.get_appointment(appointment_id)
    if row is None or row["user_id"] != callback.from_user.id or row["status"] != "confirmed":
        await callback.answer("Отзыв недоступен", show_alert=True)
        return
    await state.update_data(appointment_id=appointment_id, rating=rating)
    await state.set_state(ReviewState.text)
    await callback.message.edit_text("💬 <b>Напишите отзыв</b>\n\nМожно пропустить текст.", reply_markup=skip_review_text_keyboard(appointment_id))
    await callback.answer()


@router.message(ReviewState.text)
async def review_text(message: Message, state: FSMContext, db: Database, bot) -> None:
    text = (message.text or "").strip()
    if len(text) > 1500:
        await message.answer("Отзыв слишком длинный. Максимум 1500 символов.")
        return
    data = await state.get_data()
    ok = await db.add_review(int(data["appointment_id"]), message.from_user.id, int(data["rating"]), text or None)
    await state.clear()
    if not ok:
        await message.answer("Не удалось сохранить отзыв — возможно, он уже отправлен.", reply_markup=main_menu())
        return
    await message.answer("Спасибо за отзыв! 💖", reply_markup=main_menu())
    await bot.send_message(
        ADMIN_ID,
        "⭐ <b>Новый отзыв</b>\n\n"
        f"Клиент: {html.escape(message.from_user.full_name)}\n"
        f"Оценка: {'⭐' * int(data['rating'])}\n"
        f"Текст: {html.escape(text or '—')}\n"
        f"ID записи: <code>{data['appointment_id']}</code>",
    )


@router.callback_query(ReviewState.text, F.data.startswith("review_skip:"))
async def review_skip_text(callback: CallbackQuery, state: FSMContext, db: Database, bot) -> None:
    data = await state.get_data()
    ok = await db.add_review(int(data["appointment_id"]), callback.from_user.id, int(data["rating"]), None)
    await state.clear()
    if not ok:
        await callback.answer("Отзыв уже отправлен или недоступен", show_alert=True)
        return
    await callback.message.edit_text("Спасибо за оценку! 💖")
    await callback.message.answer("🏠 Главное меню", reply_markup=main_menu())
    await callback.answer()
    await bot.send_message(
        ADMIN_ID,
        "⭐ <b>Новая оценка</b>\n\n"
        f"Клиент: {html.escape(callback.from_user.full_name)}\n"
        f"Оценка: {'⭐' * int(data['rating'])}\n"
        f"ID записи: <code>{data['appointment_id']}</code>",
    )

```

# ===== handlers/admin.py =====
```python
import html
import logging
from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import ADMIN_ID, BUFFER_MINUTES, LUNCH_END, LUNCH_START, TIMEZONE, WORK_END, WORK_START, WORKING_DAYS
from database.db import Database
from keyboards.admin_kb import (
    admin_back_keyboard,
    admin_menu,
    blacklist_keyboard,
    block_list_keyboard,
    service_actions_keyboard,
    service_manage_keyboard,
)
from keyboards.user_kb import main_menu
from services.booking import fmt_price, ru_date
from services.waitlist import notify_waiting_list_for_date
from states.states import AdminBlacklistState, AdminBlockState, AdminServiceState

router = Router(name="admin")
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def minutes(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m


def valid_hhmm(value: str) -> bool:
    try:
        h, m = map(int, value.split(":"))
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


def overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and a_end > b_start


async def admin_denied(target) -> None:
    if isinstance(target, CallbackQuery):
        await target.answer("⛔ Доступ запрещён.", show_alert=True)
    else:
        await target.answer("⛔ Доступ запрещён.")


@router.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    await state.clear()
    await callback.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(F.data == "admin_today")
async def admin_today(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    today = datetime.now(TIMEZONE).date().isoformat()
    appointments = await db.get_appointments_for_date(today)
    blocks = await db.get_blocked_between(today, today)
    text = [f"📋 <b>Записи на сегодня — {ru_date(today)}</b>"]
    if appointments:
        for a in appointments:
            client = f"{a['full_name']}" + (f" (@{a['username']})" if a['username'] else "")
            text.append(
                f"\n🕐 <b>{a['start_time']}–{a['end_time']}</b> — {a['service_name']}\n"
                f"👤 {html.escape(client)}\n"
                f"💰 {fmt_price(int(a['price']))}\n"
                f"📝 {html.escape(a['comment'] or '—')}"
            )
    else:
        text.append("\nНет подтверждённых записей.")
    if blocks:
        text.append("\n🔒 <b>Блокировки:</b>")
        text.extend(f"• {b['start_time']}–{b['end_time']} {html.escape(b['reason'] or '')}" for b in blocks)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_today"))
    builder.row(InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin_menu"))
    await callback.message.edit_text("\n".join(text), reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "admin_week")
async def admin_week(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    start = datetime.now(TIMEZONE).date()
    end = start + timedelta(days=6)
    rows = await db.fetchall(
        """
        SELECT a.*, s.name AS service_name, s.price, u.full_name, u.username
        FROM appointments a
        JOIN services s ON s.id=a.service_id
        JOIN users u ON u.id=a.user_id
        WHERE a.status='confirmed' AND a.appointment_date BETWEEN ? AND ?
        ORDER BY a.appointment_date, a.start_time
        """,
        (start.isoformat(), end.isoformat()),
    )
    blocks = await db.get_blocked_between(start.isoformat(), end.isoformat())
    parts = [f"📆 <b>Записи на 7 дней</b>\n{ru_date(start.isoformat())} — {ru_date(end.isoformat())}"]
    current = start
    while current <= end:
        day_rows = [r for r in rows if r["appointment_date"] == current.isoformat()]
        day_blocks = [b for b in blocks if b["block_date"] == current.isoformat()]
        if day_rows or day_blocks:
            parts.append(f"\n<b>{ru_date(current.isoformat())}</b>")
            for r in day_rows:
                client = html.escape(r["full_name"])
                parts.append(f"• {r['start_time']} — {r['service_name']} — {client}")
            for b in day_blocks:
                parts.append(f"• 🔒 {b['start_time']}-{b['end_time']} — {html.escape(b['reason'] or 'блокировка')}")
        current += timedelta(days=1)
    if len(parts) == 1:
        parts.append("\nЗаписей и блокировок нет.")
    await callback.message.edit_text("\n".join(parts), reply_markup=admin_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_block")
async def admin_block_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    await state.clear()
    today = datetime.now(TIMEZONE).date().isoformat()
    blocks = await db.get_blocked_between(today, (datetime.now(TIMEZONE).date() + timedelta(days=14)).isoformat())
    text = "🔒 <b>Блокировка времени</b>\n\nВведите дату в формате <code>ДД.ММ.ГГГГ</code>."
    if blocks:
        text += "\n\n<b>Текущие блокировки:</b>\n" + "\n".join(
            f"• {b['block_date']} {b['start_time']}-{b['end_time']} — {html.escape(b['reason'] or 'без причины')}" for b in blocks
        )
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for b in blocks:
        reason = f" — {b['reason']}" if b['reason'] else ""
        builder.row(InlineKeyboardButton(
            text=f"🗑 {b['block_date']} {b['start_time']}-{b['end_time']}{reason}",
            callback_data=f"admin_delete_block:{b['id']}",
        ))
    builder.row(InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin_menu"))
    await state.set_state(AdminBlockState.date)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.message(AdminBlockState.date)
async def admin_block_date(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await admin_denied(message)
        return
    try:
        d = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат. Пример: 05.10.2026")
        return
    if d.weekday() not in WORKING_DAYS:
        await message.answer("Блокировать время можно только в рабочие дни: вторник–суббота.")
        return
    if d < datetime.now(TIMEZONE).date():
        await message.answer("Дата уже прошла.")
        return
    await state.update_data(block_date=d.isoformat())
    await state.set_state(AdminBlockState.start)
    await message.answer(f"Дата: <b>{ru_date(d.isoformat())}</b>\nВведите начало блокировки, например <code>12:00</code>.")


@router.message(AdminBlockState.start)
async def admin_block_start_time(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not valid_hhmm(value):
        await message.answer("Введите время в формате ЧЧ:ММ, например 12:00.")
        return
    if minutes(value) < minutes(WORK_START) or minutes(value) >= minutes(WORK_END):
        await message.answer(f"Время должно быть внутри рабочего дня {WORK_START}–{WORK_END}.")
        return
    await state.update_data(start=value)
    await state.set_state(AdminBlockState.end)
    await message.answer("Введите конец блокировки, например <code>13:30</code>.")


@router.message(AdminBlockState.end)
async def admin_block_end(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not valid_hhmm(value):
        await message.answer("Введите время в формате ЧЧ:ММ.")
        return
    data = await state.get_data()
    if minutes(value) <= minutes(data["start"]):
        await message.answer("Конец должен быть позже начала.")
        return
    if minutes(value) > minutes(WORK_END):
        await message.answer(f"Конец блокировки не может быть позже {WORK_END}.")
        return
    await state.update_data(end=value)
    await state.set_state(AdminBlockState.reason)
    await message.answer("Укажите причину блокировки или напишите <code>-</code>, если причина не нужна.")


@router.message(AdminBlockState.reason)
async def admin_block_reason(message: Message, state: FSMContext, db: Database) -> None:
    reason = message.text.strip()
    reason = None if reason == "-" else reason[:300]
    data = await state.get_data()
    existing = await db.fetchall(
        "SELECT start_time,end_time FROM appointments WHERE appointment_date=? AND status='confirmed'",
        (data["block_date"],),
    )
    if any(overlap(minutes(data["start"]), minutes(data["end"]), minutes(x["start_time"]), minutes(x["end_time"])) for x in existing):
        await state.clear()
        await message.answer("⚠️ В этот промежуток уже есть запись. Блокировка не создана.")
        return
    await state.update_data(reason=reason)
    await state.set_state(AdminBlockState.confirm)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data="admin_block_confirm"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_menu"))
    await message.answer(
        "🔒 <b>Проверьте блокировку</b>\n\n"
        f"Дата: {ru_date(data['block_date'])}\n"
        f"Время: <b>{data['start']}–{data['end']}</b>\n"
        f"Причина: {html.escape(reason or '—')}\n\n"
        "Подтвердить?",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(AdminBlockState.confirm, F.data == "admin_block_confirm")
async def admin_block_confirm(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    data = await state.get_data()
    try:
        block_id = await db.add_blocked_time(data["block_date"], data["start"], data["end"], data.get("reason"))
    except Exception:
        await callback.answer("Не удалось создать блокировку", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(f"✅ Блокировка #{block_id} создана.", reply_markup=admin_back_keyboard("admin_menu"))
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("admin_delete_block:"))
async def admin_delete_block(callback: CallbackQuery, db: Database, bot) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    block_id = int(callback.data.split(":", 1)[1])
    ok, date_iso = await db.delete_blocked_time(block_id)
    if not ok:
        await callback.answer("Блокировка не найдена", show_alert=True)
        return
    await callback.answer("Блокировка удалена")
    await callback.message.edit_text("✅ Блокировка удалена.", reply_markup=admin_back_keyboard("admin_menu"))
    await notify_waiting_list_for_date(bot, db, date_iso)


@router.callback_query(F.data == "admin_services")
async def admin_services(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    await state.clear()
    services = await db.get_all_services()
    await callback.message.edit_text("🛠 <b>Управление услугами</b>", reply_markup=service_manage_keyboard(services))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_service:"))
async def admin_service(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    service = await db.get_service(int(callback.data.split(":", 1)[1]))
    if service is None:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    status = "активна" if service["is_active"] else "отключена"
    text = (
        f"💅 <b>{html.escape(service['name'])}</b>\n\n"
        f"Цена: {fmt_price(int(service['price']))}\n"
        f"Длительность: {service['duration_min']} мин\n"
        f"Статус: {status}"
    )
    await callback.message.edit_text(text, reply_markup=service_actions_keyboard(service))
    await callback.answer()


@router.callback_query(F.data == "admin_service_add")
async def admin_service_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    await state.clear()
    await state.set_state(AdminServiceState.name)
    await callback.message.edit_text("➕ <b>Новая услуга</b>\n\nВведите название:")
    await callback.answer()


@router.message(AdminServiceState.name)
async def admin_service_name(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await admin_denied(message)
        return
    value = message.text.strip()
    if not value or len(value) > 120:
        await message.answer("Название должно быть от 1 до 120 символов.")
        return
    await state.update_data(name=value)
    await state.set_state(AdminServiceState.price)
    await message.answer("Введите цену в рублях, например <code>2500</code>.")


@router.message(AdminServiceState.price)
async def admin_service_price(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await admin_denied(message)
        return
    try:
        value = int(message.text.strip().replace(" ", ""))
    except ValueError:
        await message.answer("Цена должна быть целым числом.")
        return
    if value < 0 or value > 1_000_000:
        await message.answer("Введите реальную цену от 0 до 1 000 000 ₽.")
        return
    await state.update_data(price=value)
    await state.set_state(AdminServiceState.duration)
    await message.answer("Введите длительность в минутах, например <code>60</code>.")


@router.message(AdminServiceState.duration)
async def admin_service_duration(message: Message, state: FSMContext, db: Database) -> None:
    if not is_admin(message.from_user.id):
        await admin_denied(message)
        return
    try:
        value = int(message.text.strip())
    except ValueError:
        await message.answer("Длительность должна быть целым числом.")
        return
    if value <= 0 or value > 600:
        await message.answer("Длительность: от 1 до 600 минут.")
        return
    data = await state.get_data()
    service_id = await db.add_service(data["name"], int(data["price"]), value)
    await state.clear()
    await message.answer(f"✅ Услуга #{service_id} добавлена.", reply_markup=admin_menu())


async def service_edit_request(callback: CallbackQuery, state: FSMContext, db: Database, field: str, label: str) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    service_id = int(callback.data.split(":", 1)[1])
    service = await db.get_service(service_id)
    if service is None:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    await state.clear()
    await state.update_data(edit_service_id=service_id, edit_field=field)
    await state.set_state(AdminServiceState.edit_value)
    await callback.message.edit_text(f"✏️ {label}\n\nТекущее значение: <b>{html.escape(str(service[field]))}</b>\nВведите новое значение:")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_edit_name:"))
async def edit_name(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await service_edit_request(callback, state, db, "name", "Новое название")


@router.callback_query(F.data.startswith("admin_edit_price:"))
async def edit_price(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await service_edit_request(callback, state, db, "price", "Новая цена")


@router.callback_query(F.data.startswith("admin_edit_duration:"))
async def edit_duration(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await service_edit_request(callback, state, db, "duration_min", "Новая длительность")


@router.message(AdminServiceState.edit_value)
async def service_edit_value(message: Message, state: FSMContext, db: Database) -> None:
    if not is_admin(message.from_user.id):
        await admin_denied(message)
        return
    data = await state.get_data()
    field = data["edit_field"]
    raw = message.text.strip()
    if field == "name":
        value = raw
        if not value or len(value) > 120:
            await message.answer("Название должно быть от 1 до 120 символов.")
            return
    else:
        try:
            value = int(raw.replace(" ", ""))
        except ValueError:
            await message.answer("Введите целое число.")
            return
        if field == "price" and not 0 <= value <= 1_000_000:
            await message.answer("Цена должна быть от 0 до 1 000 000 ₽.")
            return
        if field == "duration_min" and not 1 <= value <= 600:
            await message.answer("Длительность должна быть от 1 до 600 минут.")
            return
    await db.update_service_field(int(data["edit_service_id"]), field, value)
    await state.clear()
    await message.answer("✅ Услуга обновлена.", reply_markup=main_menu())


@router.callback_query(F.data.startswith("admin_toggle_service:"))
async def toggle_service(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    service_id = int(callback.data.split(":", 1)[1])
    await db.toggle_service(service_id)
    service = await db.get_service(service_id)
    await callback.message.edit_text("✅ Статус услуги изменён.", reply_markup=admin_back_keyboard("admin_services"))
    await callback.answer()


@router.callback_query(F.data == "admin_blacklist")
async def admin_blacklist(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    await state.clear()
    rows = await db.get_blacklist()
    text = "🚫 <b>Чёрный список</b>"
    if rows:
        text += "\n\n" + "\n".join(
            f"• {r['user_id']} — {html.escape(r['full_name'] or 'неизвестно')} — {html.escape(r['reason'] or 'без причины')}" for r in rows
        )
    else:
        text += "\n\nСписок пуст."
    await callback.message.edit_text(text, reply_markup=blacklist_keyboard(rows))
    await callback.answer()


@router.callback_query(F.data == "admin_blacklist_add")
async def admin_blacklist_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    await state.clear()
    await state.set_state(AdminBlacklistState.user_id)
    await callback.message.edit_text("🚫 Введите Telegram ID клиента числом:")
    await callback.answer()


@router.message(AdminBlacklistState.user_id)
async def blacklist_user_id(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await admin_denied(message)
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("ID должен состоять только из цифр.")
        return
    await state.update_data(user_id=user_id)
    await state.set_state(AdminBlacklistState.reason)
    await message.answer("Введите причину или <code>-</code> для пропуска:")


@router.message(AdminBlacklistState.reason)
async def blacklist_reason(message: Message, state: FSMContext, db: Database) -> None:
    if not is_admin(message.from_user.id):
        await admin_denied(message)
        return
    data = await state.get_data()
    exists = await db.fetchone("SELECT id,full_name FROM users WHERE id=?", (int(data["user_id"]),))
    if exists is None:
        await state.clear()
        await message.answer("Такого пользователя ещё нет в базе. Сначала он должен открыть бота через /start.", reply_markup=main_menu())
        return
    reason = None if message.text.strip() == "-" else message.text.strip()[:300]
    await db.add_blacklist(int(data["user_id"]), reason)
    await state.clear()
    await message.answer("✅ Пользователь добавлен в чёрный список.", reply_markup=main_menu())


@router.callback_query(F.data.startswith("admin_blacklist_remove:"))
async def blacklist_remove(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    user_id = int(callback.data.split(":", 1)[1])
    await db.remove_blacklist(user_id)
    await callback.answer("Удалён из ЧС")
    rows = await db.get_blacklist()
    await callback.message.edit_text("🚫 <b>Чёрный список</b>", reply_markup=blacklist_keyboard(rows))


@router.callback_query(F.data == "admin_reviews")
async def admin_reviews(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    rows = await db.get_reviews(20)
    parts = ["⭐ <b>Последние отзывы</b>"]
    if not rows:
        parts.append("\nОтзывов пока нет.")
    else:
        for r in rows:
            author = html.escape(r["full_name"])
            parts.append(
                f"\n<b>{'⭐' * int(r['rating'])}</b> — {author}\n"
                f"{html.escape(r['text'] or 'Без текста')}\n"
                f"{r['appointment_date']} {r['start_time']} · {html.escape(r['service_name'])}"
            )
    await callback.message.edit_text("\n".join(parts), reply_markup=admin_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await admin_denied(callback)
        return
    s = await db.get_stats()
    rating = f"{s['avg_rating']}/5" if s["avg_rating"] is not None else "нет данных"
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{s['users']}</b>\n"
        f"📅 Всего записей: <b>{s['appointments']}</b>\n"
        f"✅ Подтверждённых всего: <b>{s['confirmed']}</b>\n"
        f"📅 Будущих записей: <b>{s['future_confirmed']}</b>\n"
        f"❌ Отменено: <b>{s['cancelled']}</b>\n"
        f"💰 Выручка по прошедшим подтверждённым визитам: <b>{fmt_price(int(s['revenue']))}</b>\n"
        f"⭐ Средняя оценка: <b>{rating}</b> ({s['review_count']} отзывов)\n"
        f"🚫 В чёрном списке: <b>{s['blacklisted']}</b>"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()

```

# ===== keyboards/__init__.py =====
```python

```

# ===== keyboards/user_kb.py =====
```python
from aiogram.types import InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Записаться"), KeyboardButton(text="📅 Мои записи")],
            [KeyboardButton(text="💰 Услуги и цены"), KeyboardButton(text="📍 Контакты")],
            [KeyboardButton(text="❌ Отменить / Перенести запись"), KeyboardButton(text="⏳ Лист ожидания")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def services_keyboard(services, prefix: str = "book_service"):
    builder = InlineKeyboardBuilder()
    for service in services:
        builder.row(
            InlineKeyboardButton(
                text=f"{service['name']} — {service['price']} ₽ / {service['duration_min']} мин",
                callback_data=f"{prefix}:{service['id']}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="user_menu"))
    return builder.as_markup()


def date_keyboard(dates, prefix: str = "book_date"):
    builder = InlineKeyboardBuilder()
    for d, label in dates:
        builder.button(text=label, callback_data=f"{prefix}:{d}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="user_menu"))
    return builder.as_markup()


def time_keyboard(date_iso: str, service_id: int, slots: list[str], prefix: str = "book_time"):
    builder = InlineKeyboardBuilder()
    for slot in slots:
        builder.button(
            text=slot,
            callback_data=f"{prefix}|{date_iso}|{service_id}|{slot.replace(':', '')}" ,
        )
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="⏳ Встать в лист ожидания", callback_data=f"wait_add:{date_iso}:{service_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ К датам", callback_data="book_back_dates"))
    return builder.as_markup()


def no_slots_keyboard(date_iso: str, service_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⏳ Встать в лист ожидания",
            callback_data=f"wait_add:{date_iso}:{service_id}",
        )
    )
    builder.row(InlineKeyboardButton(text="⬅️ К датам", callback_data="book_back_dates"))
    return builder.as_markup()


def booking_confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="book_confirm"),
        InlineKeyboardButton(text="✏️ Изменить", callback_data="book_back_dates"),
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="user_menu"))
    return builder.as_markup()


def appointments_keyboard(appointments):
    builder = InlineKeyboardBuilder()
    for appt in appointments:
        label = f"{appt['appointment_date']} {appt['start_time']} — {appt['service_name']}"
        builder.row(
            InlineKeyboardButton(text=label, callback_data=f"manage_appt:{appt['id']}")
        )
    builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="user_menu"))
    return builder.as_markup()


def appointment_actions_keyboard(appointment_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Перенести", callback_data=f"reschedule_start:{appointment_id}"),
        InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_appt:{appointment_id}"),
    )
    builder.row(InlineKeyboardButton(text="⬅️ К списку", callback_data="my_appointments"))
    return builder.as_markup()


def rating_keyboard(appointment_id: int):
    builder = InlineKeyboardBuilder()
    for rating in range(1, 6):
        builder.button(text=f"{'⭐' * rating}", callback_data=f"rating:{appointment_id}:{rating}")
    builder.adjust(1, 2, 2)
    builder.row(InlineKeyboardButton(text="⬅️ Отмена", callback_data="user_menu"))
    return builder.as_markup()


def skip_comment_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Пропустить", callback_data="skip_comment"))
    builder.row(InlineKeyboardButton(text="⬅️ Отмена", callback_data="user_menu"))
    return builder.as_markup()


def skip_review_text_keyboard(appointment_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Без текста", callback_data=f"review_skip:{appointment_id}"))
    return builder.as_markup()


def waiting_list_keyboard(waiting_rows):
    builder = InlineKeyboardBuilder()
    for row in waiting_rows:
        builder.row(
            InlineKeyboardButton(
                text=f"❌ {row['preferred_date']} — {row['service_name']}",
                callback_data=f"wait_cancel:{row['id']}",
            )
        )
    return builder.as_markup()


def reschedule_confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить перенос", callback_data="reschedule_confirm"),
        InlineKeyboardButton(text="✏️ Изменить", callback_data="reschedule_back_dates"),
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="user_menu"))
    return builder.as_markup()


def waiting_services_keyboard(services, active_rows=None):
    builder = InlineKeyboardBuilder()
    active_rows = active_rows or []
    for row in active_rows:
        builder.row(InlineKeyboardButton(
            text=f"❌ {row['preferred_date']} — {row['service_name']}",
            callback_data=f"wait_cancel:{row['id']}",
        ))
    for service in services:
        builder.row(InlineKeyboardButton(
            text=f"{service['name']} — {service['price']} ₽",
            callback_data=f"wait_service:{service['id']}",
        ))
    builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="user_menu"))
    return builder.as_markup()

```

# ===== keyboards/admin_kb.py =====
```python
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_menu():
    builder = InlineKeyboardBuilder()
    buttons = [
        ("📋 Записи на сегодня", "admin_today"),
        ("📆 Записи на неделю", "admin_week"),
        ("🔒 Заблокировать время", "admin_block"),
        ("🛠 Управление услугами", "admin_services"),
        ("🚫 Чёрный список", "admin_blacklist"),
        ("⭐ Отзывы", "admin_reviews"),
        ("📊 Статистика", "admin_stats"),
    ]
    for text, data in buttons:
        builder.row(InlineKeyboardButton(text=text, callback_data=data))
    return builder.as_markup()


def service_manage_keyboard(services):
    builder = InlineKeyboardBuilder()
    for service in services:
        status = "✅" if service["is_active"] else "⛔"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {service['name']}",
                callback_data=f"admin_service:{service['id']}",
            )
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить услугу", callback_data="admin_service_add"))
    builder.row(InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin_menu"))
    return builder.as_markup()


def service_actions_keyboard(service):
    status_text = "⛔ Выключить" if service["is_active"] else "✅ Включить"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_edit_name:{service['id']}"))
    builder.row(InlineKeyboardButton(text="💵 Цена", callback_data=f"admin_edit_price:{service['id']}"))
    builder.row(InlineKeyboardButton(text="⏱ Длительность", callback_data=f"admin_edit_duration:{service['id']}"))
    builder.row(InlineKeyboardButton(text=status_text, callback_data=f"admin_toggle_service:{service['id']}"))
    builder.row(InlineKeyboardButton(text="⬅️ К услугам", callback_data="admin_services"))
    return builder.as_markup()


def block_list_keyboard(blocks):
    builder = InlineKeyboardBuilder()
    for block in blocks:
        reason = f" — {block['reason']}" if block["reason"] else ""
        builder.row(
            InlineKeyboardButton(
                text=f"🗓 {block['block_date']} {block['start_time']}-{block['end_time']}{reason}",
                callback_data=f"admin_delete_block:{block['id']}",
            )
        )
    return builder.as_markup()


def blacklist_keyboard(rows):
    builder = InlineKeyboardBuilder()
    for row in rows:
        name = row["full_name"] or str(row["user_id"])
        builder.row(
            InlineKeyboardButton(
                text=f"🗑 {name} ({row['user_id']})",
                callback_data=f"admin_blacklist_remove:{row['user_id']}",
            )
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить в ЧС", callback_data="admin_blacklist_add"))
    builder.row(InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin_menu"))
    return builder.as_markup()


def admin_back_keyboard(callback: str = "admin_menu"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=callback))
    return builder.as_markup()

```

# ===== states/states.py =====
```python
from aiogram.fsm.state import State, StatesGroup


class BookingState(StatesGroup):
    service = State()
    date = State()
    time = State()
    comment = State()
    confirm = State()


class RescheduleState(StatesGroup):
    appointment = State()
    date = State()
    time = State()
    confirm = State()


class WaitingState(StatesGroup):
    service = State()
    date = State()


class ReviewState(StatesGroup):
    rating = State()
    text = State()


class AdminBlockState(StatesGroup):
    date = State()
    start = State()
    end = State()
    reason = State()
    confirm = State()


class AdminServiceState(StatesGroup):
    name = State()
    price = State()
    duration = State()
    edit_value = State()


class AdminBlacklistState(StatesGroup):
    user_id = State()
    reason = State()

```

# ===== middlewares/__init__.py =====
```python

```

# ===== middlewares/throttling.py =====
```python
import time
from collections import defaultdict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class SimpleThrottleMiddleware(BaseMiddleware):
    def __init__(self, interval: float = 0.7):
        self.interval = interval
        self.last_seen: dict[int, float] = defaultdict(float)

    async def __call__(self, handler, event: TelegramObject, data):
        user = getattr(event, "from_user", None)
        if user is not None:
            now = time.monotonic()
            if now - self.last_seen[user.id] < self.interval:
                return None
            self.last_seen[user.id] = now
        return await handler(event, data)

```

# ===== services/__init__.py =====
```python

```

# ===== services/booking.py =====
```python
from datetime import date, datetime, time, timedelta
from typing import Iterable

from database.db import Database
from config import (
    BOOKING_DAYS,
    BUFFER_MINUTES,
    LUNCH_END,
    LUNCH_START,
    TIMEZONE,
    WORK_END,
    WORK_START,
    WORKING_DAYS,
)


def parse_hhmm(value: str) -> time:
    hour, minute = map(int, value.split(":"))
    return time(hour, minute)


def fmt_price(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " ₽"


def ru_date(date_iso: str) -> str:
    d = date.fromisoformat(date_iso)
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    months = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    return f"{days[d.weekday()]}, {d.day} {months[d.month - 1]}"


def now_local() -> datetime:
    return datetime.now(TIMEZONE)


def next_working_days(count: int = BOOKING_DAYS) -> list[date]:
    result: list[date] = []
    current = now_local().date()
    while len(result) < count:
        if current.weekday() in WORKING_DAYS:
            result.append(current)
        current += timedelta(days=1)
    return result


def _minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and a_end > b_start


def calculate_slots_for_date(
    service_duration: int,
    date_value: date,
    appointments: Iterable,
    blocked_times: Iterable,
) -> list[str]:
    if date_value.weekday() not in WORKING_DAYS:
        return []

    day_start = _minutes(WORK_START)
    day_end = _minutes(WORK_END)
    lunch_start = _minutes(LUNCH_START)
    lunch_end = _minutes(LUNCH_END)
    today = now_local().date()
    current_minutes = now_local().hour * 60 + now_local().minute

    existing = [
        (_minutes(row["start_time"]), _minutes(row["end_time"]))
        for row in appointments
        if row["status"] == "confirmed"
    ]
    blocked = [
        (_minutes(row["start_time"]), _minutes(row["end_time"]))
        for row in blocked_times
    ]

    slots: list[str] = []
    for start in range(day_start, day_end - service_duration + 1, 15):
        end = start + service_duration
        if date_value == today and start <= current_minutes:
            continue
        if _overlap(start, end, lunch_start, lunch_end):
            continue
        if any(_overlap(start, end, b_start, b_end) for b_start, b_end in blocked):
            continue

        # Every appointment gets a 15-minute buffer after it and before the next one.
        candidate_start_with_buffer = start - BUFFER_MINUTES
        candidate_end_with_buffer = end + BUFFER_MINUTES
        conflict = False
        for e_start, e_end in existing:
            if _overlap(candidate_start_with_buffer, candidate_end_with_buffer, e_start, e_end):
                conflict = True
                break
        if conflict:
            continue
        slots.append(_hhmm(start))
    return slots


async def get_available_slots(db: Database, service_id: int, date_iso: str) -> list[str]:
    service = await db.get_service(service_id)
    if service is None or not service["is_active"]:
        return []
    appointments = await db.get_appointments_for_date(date_iso)
    blocked = await db.fetchall("SELECT * FROM blocked_times WHERE block_date=?", (date_iso,))
    return calculate_slots_for_date(
        int(service["duration_min"]),
        date.fromisoformat(date_iso),
        appointments,
        blocked,
    )


def get_end_time(start_time: str, duration_min: int) -> str:
    return _hhmm(_minutes(start_time) + duration_min)


def is_cancel_allowed(date_iso: str, start_time: str) -> bool:
    appointment_dt = datetime.combine(date.fromisoformat(date_iso), parse_hhmm(start_time)).replace(tzinfo=TIMEZONE)
    return appointment_dt - now_local() >= timedelta(hours=3)

```

# ===== services/waitlist.py =====
```python
from aiogram import Bot

from database.db import Database
from services.booking import fmt_price, get_available_slots, ru_date


async def notify_waiting_list_for_date(bot: Bot, db: Database, date_iso: str) -> None:
    rows = await db.get_active_waiting_for_date(date_iso)
    for row in rows:
        slots = await get_available_slots(db, int(row["service_id"]), date_iso)
        if not slots:
            continue
        try:
            text = (
                "🔔 <b>Появилось свободное время!</b>\n\n"
                f"Услуга: <b>{row['service_name']}</b>\n"
                f"Дата: <b>{ru_date(date_iso)}</b>\n"
                f"Стоимость: <b>{fmt_price(int(row['price']))}</b>\n\n"
                "Свободные варианты: " + ", ".join(slots[:12])
            )
            from keyboards.user_kb import time_keyboard
            await bot.send_message(
                row["user_id"],
                text,
                reply_markup=time_keyboard(date_iso, row["service_id"], slots, prefix="wait_time"),
            )
            await db.mark_waiting_notified(int(row["id"]))
        except Exception:
            # A user can have blocked the bot; this should not stop the scheduler.
            continue

```

# ===== services/reminders.py =====
```python
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    ADMIN_ID,
    REVIEW_DELAY_MINUTES,
    REMINDER_2_HOURS,
    REMINDER_24_HOURS,
    TIMEZONE,
)
from database.db import Database

logger = logging.getLogger(__name__)


def appointment_datetime(row) -> datetime:
    value = datetime.fromisoformat(f"{row['appointment_date']}T{row['start_time']}")
    return value.replace(tzinfo=TIMEZONE)


def appointment_end_datetime(row) -> datetime:
    value = datetime.fromisoformat(f"{row['appointment_date']}T{row['end_time']}")
    return value.replace(tzinfo=TIMEZONE)


def review_keyboard(appointment_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=f"review:{appointment_id}"))
    return builder.as_markup()


async def reminders_loop(bot: Bot, db: Database) -> None:
    while True:
        try:
            await process_reminders(bot, db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка в фоновых напоминаниях")
        await asyncio.sleep(60)


async def process_reminders(bot: Bot, db: Database) -> None:
    now = datetime.now(TIMEZONE)
    rows = await db.get_upcoming_for_reminders()
    for row in rows:
        start_dt = appointment_datetime(row)
        delta = start_dt - now
        total_seconds = delta.total_seconds()

        if not row["remind_24_sent"]:
            # Use a broad enough window so a temporary scheduler delay does not lose the reminder.
            if abs(total_seconds - REMINDER_24_HOURS * 3600) <= 90:
                await bot.send_message(
                    row["user_id"],
                    "⏰ <b>Напоминание о записи</b>\n\n"
                    f"Завтра в <b>{row['start_time']}</b> — {row['service_name']}.\n"
                    f"{row['appointment_date']}",
                )
                await db.mark_reminder_sent(row["id"], "24")

        if 0 <= total_seconds <= 3 * 3600 and not row["remind_2_sent"]:
            if abs(total_seconds - REMINDER_2_HOURS * 3600) <= 90:
                await bot.send_message(
                    row["user_id"],
                    "💅 <b>Напоминание</b>\n\n"
                    f"Сегодня в <b>{row['start_time']}</b> у вас запись: {row['service_name']}.",
                )
                await db.mark_reminder_sent(row["id"], "2")

    for row in await db.get_completed_without_review():
        end_dt = appointment_end_datetime(row)
        if now - end_dt >= timedelta(minutes=REVIEW_DELAY_MINUTES):
            try:
                await bot.send_message(
                    row["user_id"],
                    "✨ <b>Как прошёл ваш визит?</b>\n\n"
                    f"Будем благодарны за отзыв об услуге «{row['service_name']}».",
                    reply_markup=review_keyboard(int(row["id"])),
                )
                await db.mark_review_requested(int(row["id"]))
            except Exception:
                logger.exception("Не удалось отправить запрос отзыва: appointment=%s", row["id"])

```

# ===== requirements.txt =====
```text
aiogram==3.31.0
aiosqlite==0.22.1

```
