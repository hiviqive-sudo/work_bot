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
