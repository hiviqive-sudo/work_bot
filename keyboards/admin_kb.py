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
