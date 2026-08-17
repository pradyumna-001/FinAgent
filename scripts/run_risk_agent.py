import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio

from app.agents.risk import risk_agent_node
from app.graph.state import create_initial_state


async def main() -> None:
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-risk-manual-1",
        morning_note_id="note-risk-manual-1",
    )

    result = await risk_agent_node(state)

    risk_flags = result["risk_flags"]
    print("risk_flags count:", len(risk_flags))
    if risk_flags:
        rf = risk_flags[0]
        print("  probability:", rf["probability"])
        print("  impact:", rf["impact"])
        print("  description:", rf["description"])
        print("  severity:", rf["severity"])

    print("\ndata_freshness:", result["data_freshness"])

    flags = result["flags"]
    print("\nflags count:", len(flags))
    if flags:
        f = flags[0]
        print("  source:", f.source)
        print("  severity:", f.severity)
        print("  message:", f.message)


if __name__ == "__main__":
    asyncio.run(main())