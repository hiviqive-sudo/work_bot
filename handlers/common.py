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
