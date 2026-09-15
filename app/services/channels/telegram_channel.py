import asyncio
import logging
import time

from redis.asyncio import Redis
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.channels.base import NotePayload
from app.services.decisions import decision_key

logger = logging.getLogger(__name__)

CALLBACK_ACTIONS = ("approve", "reject")


def encode_callback(action: str, run_id: str, rec_id: int) -> str:
    if action not in CALLBACK_ACTIONS:
        raise ValueError(f"unknown callback action: {action}")
    return f"{action}:{run_id}:{rec_id}"


def decode_callback(data: str) -> tuple[str, str, int] | None:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] not in CALLBACK_ACTIONS:
        return None
    return parts[0], parts[1], int(parts[2])


def approval_keyboard(run_id: str, rec_id: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton("\u2705 aprovar", callback_data=encode_callback("approve", run_id, rec_id)),
        InlineKeyboardButton("\u274C rejeitar", callback_data=encode_callback("reject", run_id, rec_id))
    ]
    return InlineKeyboardMarkup([buttons])


class TelegramChannel:
    def __init__(self, bot: "telegram.Bot", chat_id: int, redis: Redis) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._redis = redis

    async def send_note(self, payload: NotePayload) -> None:
        text = (
            f"{payload.ticker} - {payload.action} "
            f"(confiança {payload.confidence:.0%})\n\n{payload.justification}"
        )
        await self._bot.send_message(
            chat_id=self._chat_id,
            text=text,
            reply_markup=approval_keyboard(payload.pipeline_run_id, payload.recommendation_id)
        )

    async def await_decision(self, run_id: str, rec_id: int, timeout: float) -> bool | None:
        deadline = time.monotonic() + timeout
        key = decision_key(run_id, rec_id)
        while time.monotinic() < deadline:
            value = await self._redis.get(key)
            if value is not None:
                return value == "approved" if isinstance(value, str) else value == b"approved"
            await asyncio.sleep(1.0)
        return None
    