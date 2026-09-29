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
