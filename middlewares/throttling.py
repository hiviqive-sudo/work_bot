import time
from collections import defaultdict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class SimpleThrottleMiddleware(BaseMiddleware):
    def __init__(self, interval: float = 0.7):
        self.interval = interval
        self.last_seen: dict[int, float] = defaultdict(float)

    async def __call__(self, handler, event: TelegramObject, data):
        user = getattr(event, "from_user", None)
        if user is not None:
            now = time.monotonic()
            if now - self.last_seen[user.id] < self.interval:
                return None
            self.last_seen[user.id] = now
        return await handler(event, data)
