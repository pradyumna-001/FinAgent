import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from pprint import pprint

from app.agents.quant import quant_agent_node
from app.graph.state import create_initial_state


async def main() -> None:
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-quant-manual-1",
        morning_note_id="note-quant-manual-1"
    )

    result = await quant_agent_node(state)

    print("=== quant_metrics ===")
    pprint(result["quant_metrics"])
    print("\n=== data_freshness ===")
    pprint(result["data_freshness"])
    print("\n=== flags ===")
    pprint(result["flags"])


if __name__ == "__main__":
    asyncio.run(main())