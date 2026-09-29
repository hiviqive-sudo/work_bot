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
