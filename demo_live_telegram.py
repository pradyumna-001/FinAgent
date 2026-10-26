"""Live demo: FinAgent pipeline → Telegram → approval callback.

This script demonstrates the end-to-end flow:
1. Pipeline produces a morning note with a recommendation (simulated)
2. The note is sent to Telegram with ✅/❌ inline keyboard
3. The telegram_poller (already running) listens for the callback
4. When the user clicks a button, the decision is persisted to Redis
"""

import asyncio
import os
import textwrap
from datetime import datetime, UTC
from pprint import pprint

from dotenv import load_dotenv
from redis.asyncio import Redis

from app.core.config import settings
from app.services.channels.base import NotePayload
from app.services.channels.telegram_channel import encode_callback, approval_keyboard
from app.services.decisions import decision_key, handle_decision
from app.utils.flags import DataFlag, Severity

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")

async def simulate_pipeline():
    """Simulate the FinAgent pipeline producing a morning note + recommendation."""
    # Simulate what the 5-agent pipeline would produce
    ticker = "PETR4"
    action = "buy"
    confidence = 0.87
    justification = textwrap.dedent("""\
        Technical indicators show upward momentum for PETR4.
        Selic at 13.75% favors fixed-income over equities.
        Earnings beat expectations by 8% YoY.
        Recommendation: buy on dips, target R$ 38.50.
    """)

    # Create the NotePayload (same structure the pipeline uses)
    payload = NotePayload(
        pipeline_run_id="run-live-demo-001",
        recommendation_id=42,
        ticker=ticker,
        action=action,
        confidence=confidence,
        justification=justification.strip(),
    )
    return payload


async def send_to_telegram(payload: NotePayload):
    """Send the morning note to Telegram with inline keyboard."""
    from telegram import Bot
    bot = Bot(token=BOT_TOKEN)

    text = textwrap.dedent(f"""\
        📈 {payload.ticker} — {payload.action}
        (confiança {payload.confidence:.0%})

        {payload.justification}
    """)

    reply_markup = approval_keyboard(
        payload.pipeline_run_id, payload.recommendation_id
    )

    await bot.send_message(
        chat_id=int(CHAT_ID),
        text=text,
        reply_markup=reply_markup,
    )
    print(f"✅ Message sent to Telegram chat {CHAT_ID}")
    print("   Buttons: ✅ aprovar   ❌ rejeitar")


async def wait_for_decision(redis: Redis, timeout: float = 30.0) -> bool | None:
    """Poll Redis for the decision key. Returns True=approved, False=rejected, None=timeout."""
    key = decision_key(payload.pipeline_run_id, payload.recommendation_id)
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        val = await redis.get(key)
        if val is not None:
            decided = val.decode() == "approved" if isinstance(val, bytes) else val == "approved"
            return decided
        await asyncio.sleep(1.0)
    return None


async def main():
    print("=" * 60)
    print("FinAgent Live Telegram Demo")
    print("=" * 60)

    # 1. Simulate pipeline output
    payload = await simulate_pipeline()
    print("Pipeline output:")
    print(f"   Ticker: {payload.ticker}")
    print(f"   Action: {payload.action}")
    print(f"   Confidence: {payload.confidence:.0%}")
    print(f"   Run ID: {payload.pipeline_run_id}")
    print(f"   Rec ID: {payload.recommendation_id}")

    # 2. Send to Telegram
    await send_to_telegram(payload)

    # 3. Wait for the user to click a button (via the poller processing Redis)
    print("⏳ Click ✅ aprovar or ❌ rejeitar in Telegram...")
    print("   (The poller will process the callback automatically)")
    
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    decided = await wait_for_decision(redis, timeout=30.0)
    await redis.aclose()

    # 4. Show result
    print("\n" + "=" * 60)
    if decided is True:
        print("Decision: APPROVED")
    elif decided is False:
        print("Decision: REJECTED")
    else:
        print("⏱️  Timeout: no decision received within 30s")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())