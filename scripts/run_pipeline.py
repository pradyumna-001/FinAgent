import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import sys
import time
from datetime import datetime, UTC
from pprint import pprint

from app.graph.pipeline import create_graph, dev_graph, create_initial_state

from dotenv import load_dotenv
load_dotenv()

async def main(use_postgres: bool = False):
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-123",
        morning_note_id="note-123",
    )

    config = {
        "configurable": {"thread_id": state["pipeline_run_id"]},
        "tags": [
            f"gestor_id:{state['manager_id']}",
            f"empresa:{state['company_ticker']}",
            f"data:{datetime.now(UTC).date().isoformat()}",
            f"pipeline_run_id:{state['pipeline_run_id']}",
            f"morning_note_id:{state['morning_note_id']}",
        ],
    }

    if use_postgres:
        graph = await create_graph()
        print("Using PostgresSaver")
    else:
        graph = dev_graph
        print("Using InMemorySaver (dev)")

    start = time.perf_counter()
    result = await graph.ainvoke(state, config=config)
    elapsed = time.perf_counter() - start

    pprint(f"morning_note: {result.get('morning_note')}")
    pprint(f"recommendation: {result.get('recommendation')}")
    pprint(f"confidence_scores: {result.get('confidence_scores')}")
    pprint(f"flags: {result.get('flags')}")
    print(f"\nElapsed: {elapsed:.2f}s")


if __name__ == "__main__":
    use_pg = "--postgres" in sys.argv
    if use_pg and sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(use_postgres=use_pg))