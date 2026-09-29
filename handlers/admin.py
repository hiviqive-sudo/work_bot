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
