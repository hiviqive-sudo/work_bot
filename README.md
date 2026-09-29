# Telegram-бот онлайн-записи на маникюр

Стек: Python 3.11+, aiogram 3.31.0, SQLite + aiosqlite. Бот работает через long polling.

## Локальный запуск

1. Установить Python 3.11+.
2. Создать виртуальное окружение и установить зависимости:

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
```

3. Задать переменные окружения `BOT_TOKEN` и `ADMIN_ID`.
4. Запустить:

```bash
python main.py
```

База создастся автоматически как `data/bot.db`.

## Koyeb

Загрузить проект в GitHub и создать Worker-сервис. В переменных окружения Koyeb задать:

- `BOT_TOKEN` — токен BotFather;
- `ADMIN_ID` — Telegram ID владельца/администратора.

Koyeb увидит `Procfile` и запустит `worker: python main.py`.

Для SQLite держите одну реплику/один worker: база является локальным файлом экземпляра. Для полноценного продакшена с несколькими репликами лучше перейти на PostgreSQL.

## Важные настройки

Все рабочие параметры находятся в `config.py` и могут быть переопределены переменными окружения.

Начальные услуги находятся в `config.py` и автоматически создаются при первом запуске пустой БД. После этого ими можно управлять из `/admin`.
