"""Live test: send a message through your Telegram bot.

Run with:  uv run python send_telegram_test.py

This uses the python-telegram-bot library (already installed as a #109 dep)
and the TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from .env.
"""

import asyncio
import os
from dotenv import load_dotenv

from telegram import Bot

load_dotenv()  # reads .env from cwd

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")

async def send_message():
    bot = Bot(token=BOT_TOKEN)
    text = "🧪 Live test from FinAgent — the Telegram channel is wired up.\n\n"
    text += "If you see this, the bot token and chat ID are correct.\n"
    text += "Click the ✅/❌ buttons in the message if you receive an inline keyboard."
    await bot.send_message(chat_id=int(CHAT_ID), text=text)
    print(f"Message sent to chat_id={CHAT_ID}")

if __name__ == "__main__":
    asyncio.run(send_message())