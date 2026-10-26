from redis.asyncio import Redis
from telegram import Bot

from app.core.config import settings
from app.services.channels.telegram_channel import TelegramChannel


def build_telegram_channel() -> TelegramChannel | None:
    telegram_bot_token = settings.TELEGRAM_BOT_TOKEN
    telegram_chat_id = settings.TELEGRAM_CHAT_ID
    redis_url = settings.REDIS_URL

    if (telegram_bot_token is None or telegram_chat_id is None):
        return None

    bot = Bot(token=telegram_bot_token)
    redis = Redis.from_url(redis_url, decode_responses=False)
    return TelegramChannel(bot=bot, chat_id=telegram_chat_id, redis=redis)
