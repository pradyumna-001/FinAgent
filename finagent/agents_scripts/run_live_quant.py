import os
import sys
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.graph.state import create_initial_state
from app.agents.quant import quant_agent_node

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("live-quant-run")

def main():
    load_dotenv()

    logger.info("Starting live QuantAgent dry-run script execution.")

    pipeline_run_id = f"run-live-quant-{int(datetime.now().timestamp())}"
    morning_note_id = f"note-live-quant-{int(datetime.now().timestamp())}"

    state = create_initial_state(
        pipeline_run_id=pipeline_run_id,
        morning_note_id=morning_note_id,
        manager_id=1,
        company_ticker="PETR4"
    )

    state["data_freshness"]["company"] = datetime.now(timezone.utc)

    logger.info("Executing quant_agent_node with active live netwok parameters...")

    final_state = quant_agent_node(state)

    print("\n--- LIVE RUN RESULTS ---")
    print(f"Target Ticker Analyzed: {final_state.get('company_ticker')}")
    print(f"Recorded Flags: {final_state.get('flags')}")
    
    metrics = final_state.get("quant_metrics")
    if metrics:
        print("\nCalculated Financial Metrics (Computed via Python):")
        print(f"  - P/L (Price-to-Earnings): {metrics.pe_ratio}")
        print(f"  - EV/EBITDA:                {metrics.ev_ebitda}")
        print(f"  - Dividend Yield:           {metrics.dividend_yield}%")
        print(f"  - Extracted Momentum Signal: {metrics.momentum_signal}")
    else:
        print("\nNo quantitative metrics were recorded onto the pipeline state.")
    print("------------------------\n")

if __name__ == "__main__":
    main()
