#!/usr/bin/env python
"""Debug the editor agent prompt."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.prompts.editor import EDITOR_PROMPTS
from app.graph.state import MacroOutput, CompanyEvent, QuantOutput, RiskFlag
from app.utils.flags import DataFlag, Severity

async def main():
    print("=" * 60)
    print("Debug Editor Prompt")
    print("=" * 60)
    
    # Simulate state after macro, company, quant, risk agents
    # Tavily fails -> macro_context=None, company_events=[]
    # yfinance might work or fail -> quant_metrics=None or QuoteMetrics
    # risk_agent might run or not -> risk_flags=[]
    # data_flags from tavily failures
    
    macro_context: MacroOutput | None = None
    company_events: list[CompanyEvent] = []
    quant_metrics: QuantOutput | None = None
    risk_flags: list[RiskFlag] = []
    data_flags: list[DataFlag] = [
        DataFlag(source="tavily", severity=Severity.WARNING, message="Tavily request error: Client error '432 '"),
        DataFlag(source="tavily", severity=Severity.WARNING, message="Tavily request error: Client error '432 '"),
    ]
    
    user_prompt = EDITOR_PROMPTS.build_user_prompt(
        macro_context=macro_context,
        company_events=company_events,
        quant_metrics=quant_metrics,
        risk_flags=risk_flags,
        data_flags=data_flags
    )
    
    print("USER PROMPT:")
    print("-" * 40)
    print(user_prompt)
    print("-" * 40)
    print(f"Length: {len(user_prompt)}")
    print(f"Type: {type(user_prompt)}")
    
    # Check if it's valid JSON-serializable string
    import json
    try:
        json.dumps(user_prompt)
        print("OK Valid JSON string")
    except Exception as e:
        print(f"FAIL Invalid for JSON: {e}")
    
    # Test the LLM call with this prompt
    from app.services.llm import summarize_nemotron
    print("\nTesting LLM call...")
    result = await summarize_nemotron(
        system=EDITOR_PROMPTS.system,
        user=user_prompt
    )
    if result:
        print(f"Result (first 200 chars): {repr(result[:200])}")
        # Try to parse as JSON
        import json
        try:
            parsed = json.loads(result)
            print(f"Parsed JSON keys: {list(parsed.keys())}")
            print(f"Has morning_note: {'morning_note' in parsed}")
            print(f"Has recommendation: {'recommendation' in parsed}")
            print(f"Has confidence_scores: {'confidence_scores' in parsed}")
        except json.JSONDecodeError as e:
            print(f"Not valid JSON: {e}")
    else:
        print("Result: None")

if __name__ == "__main__":
    asyncio.run(main())