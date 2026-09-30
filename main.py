import asyncio
import logging
import os

from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

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


WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "beauty_bot_secret_change_me")
PORT = int(os.getenv("PORT", "10000"))
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "")


async def main() -> None:
    logger.info("Запуск бота. Часовой пояс: %s", TIMEZONE_NAME)

    db = Database()
    await db.connect()
    await db.init_schema()

    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.workflow_data["db"] = db

    # Anti-spam throttle
    dp.message.middleware(SimpleThrottleMiddleware())
    dp.callback_query.middleware(SimpleThrottleMiddleware())

    # Routers
    dp.include_router(common_router)
    dp.include_router(user_router)
    dp.include_router(admin_router)

    reminder_task = asyncio.create_task(
        reminders_loop(bot, db),
        name="reminders",
    )

    if not BASE_URL:
        logger.warning(
            "RENDER_EXTERNAL_URL не задан. "
            "Webhook не будет установлен."
        )
    else:
        webhook_url = f"{BASE_URL}{WEBHOOK_PATH}"

        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=False,
        )

        me = await bot.get_me()

        logger.info(
            "Бот @%s готов. Webhook: %s",
            me.username,
            webhook_url,
        )

    app = web.Application()

    # Health check для Render
    async def health_check(request: web.Request) -> web.Response:
        return web.Response(text="OK")

    app.router.add_get("/", health_check)

    # Telegram webhook
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
        handle_in_background=True,
    )

    webhook_handler.register(
        app,
        path=WEBHOOK_PATH,
    )

    # Подключаем lifecycle aiogram к aiohttp
    setup_application(
        app,
        dp,
        bot=bot,
    )

    try:
        logger.info(
            "Web-сервер запускается на 0.0.0.0:%s",
            PORT,
        )

        await web._run_app(
            app,
            host="0.0.0.0",
            port=PORT,
        )

    finally:
        reminder_task.cancel()

        await asyncio.gather(
            reminder_task,
            return_exceptions=True,
        )

        await db.close()

        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Завершение по сигналу")