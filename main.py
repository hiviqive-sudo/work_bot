import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, TIMEZONE_NAME
from database.db import Database
from handlers.admin import router as admin_router
from handlers.common import router as common_router
from handlers.user import router as user_router
from middlewares.throttling import SimpleThrottleMiddleware
from services.reminders import reminders_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Запуск бота. Часовой пояс: %s", TIMEZONE_NAME)
    db = Database()
    await db.connect()
    await db.init_schema()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.workflow_data["db"] = db

    # All incoming events get a small anti-spam throttle.
    dp.message.middleware(SimpleThrottleMiddleware())
    dp.callback_query.middleware(SimpleThrottleMiddleware())

    dp.include_router(common_router)
    dp.include_router(user_router)
    dp.include_router(admin_router)

    reminder_task = asyncio.create_task(reminders_loop(bot, db), name="reminders")

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        me = await bot.get_me()
        logger.info("Бот @%s готов. Long polling запущен.", me.username)
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        await asyncio.gather(reminder_task, return_exceptions=True)
        await db.close()
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Завершение по сигналу")
