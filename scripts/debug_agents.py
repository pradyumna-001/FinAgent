#!/usr/bin/env python
"""Debug script to test each agent individually."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.graph.state import create_initial_state

# Test Tavily
async def test_tavily():
    from app.services.tavily import TavilyService
    print("Testing Tavily...")
    tavily = TavilyService(api_key=settings.TAVILY_API_KEY)
    result = await tavily.search(
        query="macro news Brazil",
        include_domains=["bcb.gov.br", "ibge.gov.br", "br.reuters.com", "bloomberg.com.br"],
        max_results=5
    )
    print(f"  Articles: {len(result.articles)}")
    if result.error:
        print(f"  Error: {result.error.message} (severity: {result.error.severity})")
    if result.articles:
        print(f"  First: {result.articles[0].title[:80]}...")
    return result

# Test NVIDIA summarize
async def test_nvidia_summarize():
    from app.services.llm import summarize
    print("Testing NVIDIA summarize...")
    result = await summarize(
        system="You are a macroeconomic analyst covering the Brazilian market.",
        user="Summarize: Selic rate held at 13.75%. Inflation at 4.6%. GDP growth 0.9%."
    )
    print(f"  Result: {result[:100] if result else 'None'}...")
    return result

# Test NVIDIA nemotron
async def test_nvidia_nemotron():
    from app.services.llm import summarize_nemotron
    print("Testing NVIDIA Nemotron...")
    result = await summarize_nemotron(
        system="You are an editor. Respond only with JSON.",
        user="Generate a morning note for PETR4. Return JSON with morning_note, recommendation, confidence_scores."
    )
    print(f"  Result: {result[:200] if result else 'None'}...")
    return result

# Test yfinance
async def test_yfinance():
    from app.services.yfinance import YfinanceService
    print("Testing yfinance...")
    yf = YfinanceService()
    result = await yf.search("PETR4.SA")
    print(f"  Metrics: {result.metrics}")
    if result.error:
        print(f"  Error: {result.error}")
    return result

async def main():
    print("=" * 60)
    print("Agent Debug Tests")
    print("=" * 60)
    
    await test_tavily()
    print()
    await test_nvidia_summarize()
    print()
    await test_nvidia_nemotron()
    print()
    await test_yfinance()
    print()

if __name__ == "__main__":
    asyncio.run(main())