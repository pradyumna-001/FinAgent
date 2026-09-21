import logging

from telegram import Bot, Message
from telegram.error import TelegramError

from app.core.config import settings
from app.services.decisions import handle_decision
from app.services.channels.telegram_channel import decode_callback
from app.utils.flags import DataFlag, Severity

logger = logging.getLogger(__name__)


async def telegram_polling_loop() -> DataFlag:
    if not settings.TELEGRAM_BOT_TOKEN:
        return DataFlag(
            source="telegram",
            severity=Severity.INFO,
            message="no TELEGRAM_BOT_TOKEN configured — gate auto-passes"
        )

    from redis.asyncio import Redis

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)

    seen_key = "telegram:seen_update_ids"

    try:
        while True:
            updates = await bot.get_updates(
                timeout=settings.TELEGRAM_POLL_TIMEOUT_S,
                allowed_updates=["message", "callback_query"]
            )
            for update in updates:
                if update.update_id <= 0:
                    continue
                if await redis.sismember(seen_key, str(update.update_id)):
                    continue
                await redis.sadd(seen_key, str(update.update_id))
                await redis.expire(seen_key, 86400)

                cq = update.callback_query
                if cq is None or not cq.data:
                    continue

                parsed = decode_callback(cq.data)
                if parsed is None:
                    logger.warning("malformed callback_data", extra={"data": cq.data})
                    await bot.answer_callback_query(cq.id, "dados inválidos")
                    continue

                action, run_id, rec_id = parsed

                decided = await handle_decision(redis, run_id, rec_id, action == "approve")
                if decided is None:
                    await bot.answer_callback_query(cq.id, "já registrado")
                    continue

                try:
                    await bot.answer_callback_query(cq.id, "registrado")
                    msg = cq.message
                    if isinstance(msg, Message):
                        await bot.edit_message_text(
                            chat_id=msg.chat_id,
                            message_id=msg.message_id,
                            text=f"{msg.text}\n\nDecisão: {'aprovado' if decided else 'rejeitado'}",
                        )
                    else:
                        logger.warning("failed to answer/edit callback")
                except TelegramError as e:
                    logger.warning("failed to answer/edit callback", exc_info=e)
                    await bot.answer_callback_query(cq.id, "erro ao processar")
    finally:
        await redis.aclose()

    return DataFlag(
        source="telegram",
        severity=Severity.INFO,
        message="telegram poller stopped"
    )
