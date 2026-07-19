import os
import asyncio
import logging
from json import dumps

logging.basicConfig(level=logging.INFO)

from app.graph.state import create_initial_state
from app.agents.macro import macro_agent_node
from app.agents.company import company_agent_node
from app.agents.quant import quant_agent_node
from app.agents.risk import risk_agent_node

async def run_real_data_deliverable_check():
    print("Initializing real data state for PETR4")
    state = create_initial_state(
        pipeline_run_id="smoke-test-real-data",
        morning_note_id="note-real-data",
        manager_id=1,
        company_ticker="PETR4"
    )

    print("Step 1: Running base agents to gather real live data...")
    state = macro_agent_node(state)
    state = company_agent_node(state)
    state = quant_agent_node(state)

    print("Step 2: Running RiskAgent to find adversarial vulnerabilities...")
    final_state = risk_agent_node(state)

    print("--- DELIVERABLE RESULTS (REAL RISK FLAGS IDENTIFIED) ---")
    if not final_state["risk_flags"]:
        print("Failure: No risks were identified.")
    else:
        for idx, flag in enumerate(final_state["risk_flags"], 1):
            print(f"\n[Risk #{idx}] Type: {flag.risk_type} | Severity: {flag.severity.upper()}")
            print(f"Description: {flag.description}")

    print("\n-----------------------------------------------------------")

if __name__ == "__main__":
    asyncio.run(run_real_data_deliverable_check())
