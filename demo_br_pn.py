"""Live demo: FinAgent pipeline → Telegram (Brazilian Portuguese full morning note).

Demonstrates end-to-end flow with:
- Full morning note in Brazilian Portuguese (from EditorAgent)
- Recommendation with action/justification/confidence
- Inline keyboard ✅/❌ for approval
- Poller processes the callback and persists decision to Redis
"""

import asyncio
import os
import json
from datetime import datetime, UTC

from dotenv import load_dotenv
from redis.asyncio import Redis

from app.core.config import settings
from app.agents.editor import editor_agent_node
from app.graph.state import create_initial_state, AgentState
from app.services.channels.telegram_channel import approval_keyboard
from app.services.decisions import decision_key, handle_decision
from app.utils.flags import DataFlag, Severity

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")


async def make_macro_context():
    """Simulate MacroAgent output."""
    return {
        "selic": 13.75,
        "ipca_12m": 4.87,
        "dolar": 5.15,
        "contexto": "Ambiente de juros altos e inflação dentro da meta.",
    }


async def make_company_events():
    """Simulate CompanyAgent output."""
    return [
        {"title": "Resultado 4T24", "summary": "Lucro líquido de R$ 8,7 bi, acima do esperado."},
        {"title": "Dividendo", "summary": "Proposta de dividendos de R$ 0,50 por ação."},
    ]


async def make_quant_metrics():
    """Simulate QuantAgent output."""
    return {
        "action": "buy",
        "confidence": 0.87,
        "justification": "Indicadores técnicos de alta + valuation atrativo.",
        "dev_ibov": -0.02,
    }


async def make_risk_flags():
    """Simulate RiskAgent output."""
    return [
        {"probability": 0.15, "impact": "medium", "description": "Volatilidade do petróleo internacional", "severity": "WARNING"},
    ]


async def main():
    print("=" * 70)
    print("FinAgent Live Demo - Morning Note em Português Brasileiro")
    print("=" * 70)

    # 1. Build initial state like the pipeline does
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-br-demo-001",
        morning_note_id="note-br-001",
    )

    # 2. Run the EditorAgent (this is where the Portuguese morning note is generated)
    print("\nRodando EditorAgent (sintese em portugues)...")
    result = await editor_agent_node(state)

    morning_note = result.get("morning_note")
    recommendation = result.get("recommendation")
    confidence_scores = result.get("confidence_scores")
    flags = result.get("flags", [])

    if not morning_note or not recommendation:
        print("Editor failed to produce output. Flags:", [f.message for f in flags])
        return

    print("\nEditorAgent produziu output em portugues:")
    print("-" * 70)
    print(morning_note)
    print("-" * 70)

    # Display the recommendation
    action = recommendation.get("action") if isinstance(recommendation, dict) else "buy"
    justification = recommendation.get("justification") if isinstance(recommendation, dict) else "Justificativa"
    confidence = recommendation.get("confidence") if isinstance(recommendation, dict) else 0.87
    print(f"\nRecomendacao: {action.upper()}")
    print(f"Confianca: {confidence:.0f}%")
    print(f"Justificativa: {justification[:100]}{'...' if len(justification) > 100 else ''}")

    # 3. Send the full morning note to Telegram with inline keyboard
    print("\nEnviando morning note para Telegram...")
    payload = type("Payload", (), {})()
    payload.pipeline_run_id = state["pipeline_run_id"]
    payload.recommendation_id = state.get("recommendation_id", 1)
    payload.ticker = state.get("company_ticker", "PETR4")
    payload.action = action
    payload.confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.87
    payload.justification = justification if isinstance(recommendation, dict) else "Justificativa do analista."

    reply_markup = approval_keyboard(payload.pipeline_run_id, payload.recommendation_id)

    from telegram import Bot
    bot = Bot(token=BOT_TOKEN)

    await bot.send_message(
        chat_id=int(CHAT_ID),
        text=morning_note,
        reply_markup=reply_markup,
    )
    print("Morning note enviado para o Telegram!")

    # 4. Wait for the user to click a button
    print("\nAgora clique em aprovar ou rejeitar no Telegram...")
    print("O poller vai processar o callback automaticamente.")

    # 5. Poll Redis for the decision
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    key = decision_key(payload.pipeline_run_id, payload.recommendation_id)
    deadline = asyncio.get_event_loop().time() + 30.0
    decided = None
    while asyncio.get_event_loop().time() < deadline:
        val = await redis.get(key)
        if val is not None:
            decided = val == "approved" if isinstance(val, str) else val.decode() == "approved"
            break
        await asyncio.sleep(1.0)
    await redis.aclose()

    # 6. Show the result
    print("\n" + "=" * 70)
    if decided is True:
        print("DECIAO: APROVADO")
    elif decided is False:
        print("DECIAO: REJEITADO")
    else:
        print("Tempo esgotado: nenhuma decisao registrada em 30s")
    print("=" * 70)

    print("\nPrximo passo: Issue #110 - approval gate no pipeline LangGraph.")


if __name__ == "__main__":
    asyncio.run(main())