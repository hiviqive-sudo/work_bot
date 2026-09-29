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
