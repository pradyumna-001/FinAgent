import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import sys
import time
from datetime import datetime, UTC
from pprint import pprint

from app.graph.pipeline import compile_graph, dev_graph, create_initial_state

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
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from app.db.session import engine

        dsn = str(engine.url).replace("postgresql+asyncpg://", "postgresql://")
        print("Using PostgresSaver")
        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            await run_graph(compile_graph(saver), state, config)
        return

    print("Using InMemorySaver (dev)")
    await run_graph(dev_graph, state, config)


async def run_graph(graph, state, config):
    start = time.perf_counter()
    result = await graph.ainvoke(state, config=config)
    elapsed = time.perf_counter() - start

    if "__interrupt__" in result:
        print("Pipeline parked at approval_gate — decide via Telegram, then resume.")

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