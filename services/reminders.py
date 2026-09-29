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
