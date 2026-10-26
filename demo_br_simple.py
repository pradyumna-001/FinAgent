"""Simple demo: send a Brazilian Portuguese morning note to Telegram with approval keyboard.

This demonstrates:
1. A full morning note in Brazilian Portuguese
2. The inline keyboard ✅/❌ for approval
3. The poller will process the callback decision
"""

import asyncio
import os
from dotenv import load_dotenv

from telegram import Bot
from app.services.channels.telegram_channel import approval_keyboard

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")

async def main():
    print("Enviando morning note em português para o Telegram...")

    # Full Brazilian Portuguese morning note
    morning_note = """Morning Note - PETR4 - 15/01/2025

Contexto Macro:
- Selic: 13.75% ao ano
- IPCA-12m: 4.87%
- Dólar: R$ 5,15

Eventos da Empresa:
- Resultado 4T24: Lucro líquido de R$ 8,7 bi, acima do esperado.
- Dividendo: Proposta de R$ 0,50 por ação.

Riscos:
- Volatilidade do petróleo internacional (probabilidade 15%, impacto médio)

Recomendação:
Ação: buy
Justificativa: Indicadores técnicos de alta + valuation atrativo após ajuste de prêmios de risco.
Confiança: 87%

Sugestão de entrada: compra em patamares entre R$ 38,00 e R$ 39,00.
Objetivo de preço: R$ 42,00 para horizonte de 12 meses.
"""

    bot = Bot(token=BOT_TOKEN)
    keyboard = approval_keyboard("live-demo-001", 1)

    await bot.send_message(
        chat_id=int(CHAT_ID),
        text=morning_note,
        reply_markup=keyboard,
    )
    print("Morning note em português enviado para o Telegram!")
    print("Agora clique em aprovar ou rejeitar.")

asyncio.run(main())