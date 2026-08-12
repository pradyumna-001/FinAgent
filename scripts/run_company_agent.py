import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from pprint import pprint

from app.agents.company import company_agent_node
from app.graph.state import create_initial_state


async def main() -> None:
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-company-manual-1",
        morning_note_id="note-company-manual-1"
    )

    result = await company_agent_node(state)

    print("=== company_events ===")
    pprint(result["company_events"])
    print("\n=== data_freshness ===")
    pprint(result["data_freshness"])
    print("\n=== flags ===")
    pprint(result["flags"])


if __name__ == "__main__":
    asyncio.run(main())