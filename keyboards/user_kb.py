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
