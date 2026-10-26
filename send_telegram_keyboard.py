"""Live test: send a Telegram message with ✅/❌ inline keyboard.

Run with:  uv run python send_telegram_keyboard.py

This uses the approval_keyboard function from app.services.channels.telegram_channel
and your .env credentials.
"""

import asyncio
import os
from dotenv import load_dotenv

from telegram import Bot
from app.services.channels.telegram_channel import encode_callback, approval_keyboard

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")

async def send_keyboard():
    bot = Bot(token=BOT_TOKEN)
    text = "🧪 Live test — aprovar ou rejeitar esta recomendação:\n\n"
    text += "Este é um teste do canal Telegram do FinAgent.\n"
    reply_markup = approval_keyboard("test-run-123", 42)
    await bot.send_message(chat_id=int(CHAT_ID), text=text, reply_markup=reply_markup)
    print("Message with keyboard sent to chat_id={CHAT_ID}")

if __name__ == "__main__":
    asyncio.run(send_keyboard())