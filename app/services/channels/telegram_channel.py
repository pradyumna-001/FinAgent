"""Telegram channel implementation for delivering morning-note recommendations.

Sends formatted buy/sell/keep recommendations to a Telegram chat with an
inline approval keyboard, and polls Redis for manager decisions.
"""

import asyncio
import logging
import time

import telegram
from redis.asyncio import Redis
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.channels.base import NotePayload
from app.services.decisions import decision_key

logger = logging.getLogger(__name__)

CALLBACK_ACTIONS = ("approve", "reject")


def encode_callback(action: str, run_id: str, rec_id: int) -> str:
    """Encode a manager decision callback into a telegram callback_data string.

    Args:
        action: "approve" or "reject".
        run_id: Pipeline run identifier.
        rec_id: Recommendation database id.

    Returns:
        String in the form "action:run_id:rec_id".

    Raises:
        ValueError: If action is not a valid CALLBACK_ACTIONS member.
    """
    if action not in CALLBACK_ACTIONS:
        raise ValueError(f"unknown callback action: {action}")
    return f"{action}:{run_id}:{rec_id}"


def decode_callback(data: str) -> tuple[str, str, int] | None:
    """Decode a telegram callback_data string back into (action, run_id, rec_id).

    Args:
        data: Callback data string received from Telegram.

    Returns:
        Tuple of (action, run_id, rec_id), or None if the data is malformed
        or the action is invalid.
    """
    parts = data.split(":")
    if len(parts) != 3 or parts[0] not in CALLBACK_ACTIONS:
        return None
    return parts[0], parts[1], int(parts[2])


def approval_keyboard(run_id: str, rec_id: int) -> InlineKeyboardMarkup:
    """Build an inline keyboard with Approve/Reject buttons for a recommendation.

    Args:
        run_id: Pipeline run identifier.
        rec_id: Recommendation database id.

    Returns:
        InlineKeyboardMarkup with two buttons (approve, reject).
    """
    buttons = [
        InlineKeyboardButton("\u2705 aprovar", callback_data=encode_callback("approve", run_id, rec_id)),
        InlineKeyboardButton("\u274C rejeitar", callback_data=encode_callback("reject", run_id, rec_id))
    ]
    return InlineKeyboardMarkup([buttons])


class TelegramChannel:
    """Delivery channel that sends recommendations via Telegram bot.

    Sends a formatted note message with an inline approval keyboard to a
    configured chat, then polls Redis for the manager's decision.
    """

    def __init__(self, bot: "telegram.Bot", chat_id: int, redis: Redis) -> None:
        """Initialize the channel with a Telegram bot, chat id, and Redis client.

        Args:
            bot: Configured telegram.Bot instance.
            chat_id: Target chat id for message delivery.
            redis: Redis async client for decision polling.
        """
        self._bot = bot
        self._chat_id = chat_id
        self._redis = redis

    async def send_note(self, payload: NotePayload) -> None:
        """Deliver a morning-note recommendation to the Telegram chat.

        Formats the ticker, action, confidence, and justification into a
        message with an inline Approve/Reject keyboard attached.

        Args:
            payload: NotePayload containing the recommendation to deliver.
        """
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
        """Poll Redis for a manager decision on a recommendation.

        Args:
            run_id: Pipeline run identifier.
            rec_id: Recommendation database id.
            timeout: Maximum seconds to wait for a decision.

        Returns:
            True if approved, False if rejected, None on timeout.
        """
        deadline = time.monotonic() + timeout
        key = decision_key(run_id, rec_id)
        while time.monotonic() < deadline:
            value = await self._redis.get(key)
            if value is not None:
                return value == "approved" if isinstance(value, str) else value == b"approved"
            await asyncio.sleep(1.0)
        return None
