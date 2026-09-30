import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv(override=True)

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
