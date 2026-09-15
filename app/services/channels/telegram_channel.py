import logging

from telegram import InlineKeyBoardButton, InlineKeyboardMarkup

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
        InlineKeyBoardButton("")
    ]