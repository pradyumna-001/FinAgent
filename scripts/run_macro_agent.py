import asyncio
from pprint import pprint

from app.agents.macro import macro_agent_node
from app.graph.state import create_initial_state


async def main() -> None:
    # Create a minimal state. Replace values as needed.
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-manual-1",
        morning_note_id="note-manual-1",
    )

    result = await macro_agent_node(state)

    print("=== macro_context ===")
    pprint(result["macro_context"])
    print("\n=== data_freshness ===")
    pprint(result["data_freshness"])
    print("\n=== flags ===")
    pprint(result["flags"])


if __name__ == "__main__":
    asyncio.run(main())