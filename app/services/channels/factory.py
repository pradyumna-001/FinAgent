"""Channel factory for building delivery channel instances.

Provides build_telegram_channel() which constructs a TelegramChannel
from application settings, or returns None when Telegram is not configured.
"""

from redis.asyncio import Redis
from telegram import Bot

from app.core.config import settings
from app.services.channels.telegram_channel import TelegramChannel


def build_telegram_channel() -> TelegramChannel | None:
    """Build a TelegramChannel from settings, or None if not configured.

    Reads TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, and REDIS_URL from
    application settings. Returns None when bot token or chat id is missing,
    signaling that the send node should treat channel delivery as unavailable.

    Returns:
        TelegramChannel if credentials are present, None otherwise.
    """
    telegram_bot_token = settings.TELEGRAM_BOT_TOKEN
    telegram_chat_id = settings.TELEGRAM_CHAT_ID
    redis_url = settings.REDIS_URL

    if (telegram_bot_token is None or telegram_chat_id is None):
        return None

    bot = Bot(token=telegram_bot_token)
    redis = Redis.from_url(redis_url, decode_responses=False)
    return TelegramChannel(bot=bot, chat_id=telegram_chat_id, redis=redis)
