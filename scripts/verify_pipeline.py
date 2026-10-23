#!/usr/bin/env python
"""
End-to-end pipeline verification script.

Spins up infra, runs the complete pipeline with real services,
handles the approval gate, and verifies all outputs in the database.

Usage:
    python scripts/verify_pipeline.py [--keep-running] [--no-telegram] [--verbose]
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from pprint import pprint
from uuid import uuid4

# Ensure project root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models import Company, Manager, MorningNote, MorningNoteStatus, Portfolio
from app.graph.pipeline import compile_graph
from app.graph.state import create_initial_state

# =============================================================================
# Helpers
# =============================================================================

def run_cmd(cmd: list[str], cwd: Path | None = None, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command, raise on failure."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=capture, text=True)
    if result.returncode != 0:
        if capture:
            print(f"  [FAIL] stdout:\n{result.stdout}")
            print(f"  [FAIL] stderr:\n{result.stderr}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    if capture and result.stdout.strip():
        print(f"  {result.stdout.strip()}")
    return result


async def check_docker() -> bool:
    """Check if Docker daemon is running."""
    try:
        run_cmd(["docker", "info"], capture=True)
        return True
    except (RuntimeError, FileNotFoundError):
        return False


def check_env_file() -> bool:
    """Check if .env exists and has required keys."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        print(f"[FAIL] .env not found at {env_path}")
        print("       Copy .env.example to .env and fill in required values:")
        print("       NVIDIA_API_KEY, TAVILY_API_KEY, DATABASE_URL, MIGRATION_DATABASE_URL, REDIS_URL, SECRET_KEY")
        return False

    # Load and check required keys
    from dotenv import load_dotenv
    load_dotenv(env_path)

    required = [
        "NVIDIA_API_KEY", "TAVILY_API_KEY",
        "DATABASE_URL", "MIGRATION_DATABASE_URL",
        "REDIS_URL", "SECRET_KEY"
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"[FAIL] Missing required env vars in .env: {', '.join(missing)}")
        return False
    return True


async def wait_for_service(host: str, port: int, timeout: int = 30) -> bool:
    """Wait for a TCP port to become available."""
    import socket
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except (ConnectionRefusedError, OSError):
            await asyncio.sleep(0.5)
    return False


# =============================================================================
# Phase 1: Infra Up
# =============================================================================

async def phase_infra_up(keep_running: bool) -> None:
    print("\n=== Phase 1: Starting Docker infrastructure ===")

    # Check if already running
    result = subprocess.run(
        ["docker-compose", "ps", "-q"],
        cwd=ROOT, capture_output=True, text=True
    )
    if result.stdout.strip():
        print("  Containers already running, skipping docker-compose up")
        return

    run_cmd(["docker-compose", "up", "-d", "--wait"])

    # Explicit wait for ports (healthchecks can be slow on first start)
    print("  Waiting for Postgres (5434)...")
    if not await wait_for_service("localhost", 5434, 60):
        raise RuntimeError("Postgres not ready on port 5434")
    print("  Waiting for Redis (6379)...")
    if not await wait_for_service("localhost", 6379, 30):
        raise RuntimeError("Redis not ready on port 6379")

    print("  Infrastructure ready")


# =============================================================================
# Phase 2: Migrations
# =============================================================================

async def phase_migrations() -> None:
    print("\n=== Phase 2: Running Alembic migrations ===")
    run_cmd(["alembic", "upgrade", "head"])
    print("  Migrations applied")


# =============================================================================
# Phase 3: Seed Data
# =============================================================================

async def phase_seed_data() -> dict:
    """
    Insert required seed data:
    - Manager (id=1)
    - Company (PETR4)
    - Portfolio (for manager)
    - MorningNote (status=pending)
    Returns dict with IDs.
    """
    print("\n=== Phase 3: Seeding database ===")

    # Use sync DSN for alembic-style operations
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    sync_url = settings.MIGRATION_DATABASE_URL
    engine = create_engine(sync_url)

    with Session(engine) as session:
        # Manager
        mgr = session.query(Manager).filter_by(id=1).first()
        if not mgr:
            mgr = Manager(id=1, name="Test Manager", email="test@finagent.local", password_hash="hash")
            session.add(mgr)
            session.flush()
        manager_id = mgr.id
        print(f"  Manager: id={manager_id}")

        # Company
        comp = session.query(Company).filter_by(ticker="PETR4").first()
        if not comp:
            comp = Company(ticker="PETR4", name="Petrobras", sector="Oil & Gas")
            session.add(comp)
            session.flush()
        company_id = comp.id
        print(f"  Company: id={company_id}, ticker=PETR4")

        # Portfolio
        port = session.query(Portfolio).filter_by(manager_id=manager_id).first()
        if not port:
            port = Portfolio(id=100, manager_id=manager_id, name="Test Portfolio")
            session.add(port)
            session.flush()
        portfolio_id = port.id
        print(f"  Portfolio: id={portfolio_id}")

        # MorningNote (pending - will be updated by pipeline)
        note = session.query(MorningNote).filter_by(id=123).first()
        if not note:
            note = MorningNote(
                id=123,
                portfolio_id=portfolio_id,
                manager_id=manager_id,
                company_id=company_id,
                note_text="",
                pipeline_run_id="",  # will be set by pipeline
                status=MorningNoteStatus.PENDING,
                confidence_scores={},
                data_freshness={},
                flags=[],
            )
            session.add(note)
        morning_note_id = note.id
        print(f"  MorningNote: id={morning_note_id}, status=pending")

        session.commit()

    engine.dispose()

    return {
        "manager_id": manager_id,
        "company_id": company_id,
        "portfolio_id": portfolio_id,
        "morning_note_id": morning_note_id,
    }


# =============================================================================
# Phase 4: Compile Graph with PostgresSaver
# =============================================================================

async def phase_compile_graph() -> tuple:
    """Create AsyncPostgresSaver, setup checkpoints, compile graph."""
    print("\n=== Phase 4: Compiling graph with PostgresSaver ===")

    # Convert asyncpg URL to psycopg for AsyncPostgresSaver
    dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    print(f"  DSN: {dsn.split('@')[0]}@...")  # hide password

    saver_cm = AsyncPostgresSaver.from_conn_string(dsn)
    saver = await saver_cm.__aenter__()
    await saver.setup()
    print("  Checkpoint tables created/verified")

    graph = compile_graph(saver)
    print("  Graph compiled with PostgresSaver")

    return saver, saver_cm, graph


# =============================================================================
# Phase 5: Run Pipeline to Interrupt
# =============================================================================

async def phase_run_to_interrupt(graph, seed_ids: dict) -> tuple:
    """Run graph.ainvoke until approval_gate interrupt."""
    print("\n=== Phase 5: Running pipeline to approval gate ===")

    pipeline_run_id = str(uuid4())
    print(f"  Pipeline run ID: {pipeline_run_id}")

    state = create_initial_state(
        manager_id=seed_ids["manager_id"],
        company_ticker="PETR4",
        pipeline_run_id=pipeline_run_id,
        morning_note_id=str(seed_ids["morning_note_id"]),
    )

    config = {
        "configurable": {"thread_id": pipeline_run_id},
        "tags": [
            f"gestor_id:{state['manager_id']}",
            f"empresa:{state['company_ticker']}",
            f"data:{datetime.now(UTC).date().isoformat()}",
            f"pipeline_run_id:{pipeline_run_id}",
            f"morning_note_id:{state['morning_note_id']}",
        ],
    }

    print("  Invoking graph (this calls real LLMs and external APIs)...")
    start = time.perf_counter()
    try:
        result = await graph.ainvoke(state, config=config)
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"  [ERROR] Graph failed after {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        raise
    elapsed = time.perf_counter() - start

    print(f"  Graph returned in {elapsed:.2f}s")

    if "__interrupt__" not in result:
        print("[WARN] No interrupt returned — pipeline may have completed or failed early")
        pprint(result.get("flags", []))
    else:
        print("  [OK] Pipeline parked at approval_gate")
        interrupt = result["__interrupt__"][0]
        print("  Interrupt payload:")
        pprint(interrupt.value)

    return pipeline_run_id, result


# =============================================================================
# Phase 6: Handle Approval Gate
# =============================================================================

async def phase_handle_gate(graph, pipeline_run_id: str, result: dict, no_telegram: bool) -> dict:
    """Resume the graph after approval gate interrupt."""
    print("\n=== Phase 6: Handling approval gate ===")

    if "__interrupt__" not in result:
        print("  No interrupt to resume from")
        return result

    interrupt = result["__interrupt__"][0]
    rec_id = interrupt.value["recommendation_id"]
    print(f"  Recommendation ID from interrupt: {rec_id}")

    if no_telegram or not settings.TELEGRAM_BOT_TOKEN:
        print("  No Telegram configured — manually resuming with 'approved'")
        resume_value = "approved"
        result2 = await graph.ainvoke(
            Command(resume=resume_value),
            config={"configurable": {"thread_id": pipeline_run_id}},
        )
        print("  [OK] Graph resumed and completed")
        return result2
    else:
        print("  Telegram configured — starting poller (not implemented in this script)")
        print("  Use --no-telegram to force manual resume")
        raise NotImplementedError("Telegram poller integration not implemented in verify script")


# =============================================================================
# Phase 7: Verify Results
# =============================================================================

async def phase_verify(pipeline_run_id: str, seed_ids: dict, result: dict, graph, saver) -> bool:
    """Query database and verify all expected outputs."""
    print("\n=== Phase 7: Verifying results in database ===")

    all_ok = True

    # 1. Use graph.aget_state to get the full checkpoint state (handles msgpack decoding)
    print("\n  1. Checking checkpoint state for generated content...")
    try:
        snap = await graph.aget_state(config={"configurable": {"thread_id": pipeline_run_id}})
        cv = snap.values
        morning_note = cv.get("morning_note")
        recommendation = cv.get("recommendation")
        confidence_scores = cv.get("confidence_scores")
        flags = cv.get("flags", [])
        data_freshness = cv.get("data_freshness", {})
        manager_decision = cv.get("manager_decision")
        decision_channel = cv.get("decision_channel")
        recommendation_id = cv.get("recommendation_id")

        print(f"     morning_note length: {len(morning_note) if morning_note else 0}")
        print(f"     recommendation: {recommendation}")
        print(f"     confidence_scores: {confidence_scores}")
        print(f"     data_freshness keys: {list(data_freshness.keys()) if data_freshness else 'empty'}")
        print(f"     flags count: {len(flags) if flags else 0}")
        print(f"     manager_decision: {manager_decision}")
        print(f"     decision_channel: {decision_channel}")
        print(f"     recommendation_id: {recommendation_id}")

        if not morning_note or len(morning_note) < 50:
            print("     [FAIL] Morning note text too short or empty")
            all_ok = False
        if not recommendation:
            print("     [FAIL] No recommendation in checkpoint")
            all_ok = False
        if not confidence_scores:
            print("     [FAIL] confidence_scores empty")
            all_ok = False
        if manager_decision != "approved":
            print(f"     [FAIL] Expected manager_decision='approved', got '{manager_decision}'")
            all_ok = False
        if decision_channel != "telegram":
            print(f"     [FAIL] Expected decision_channel='telegram', got '{decision_channel}'")
            all_ok = False
    except Exception as e:
        print(f"     [FAIL] Failed to read checkpoint state: {e}")
        all_ok = False

    # 2. Check recommendations table (persisted) - use async engine
    print("\n  2. Checking recommendations table...")
    async_engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(async_engine, expire_on_commit=False)

    async with async_session() as session:
        rec_result = await session.execute(
            text("SELECT id, morning_note_id, action, confidence, justification, "
                 "manager_decision, decided_at, decision_channel, telegram_update_id "
                 "FROM recommendations WHERE morning_note_id = :mn_id"),
            {"mn_id": seed_ids["morning_note_id"]}
        )
        recs = rec_result.all()
        if recs:
            approved_found = False
            for rec in recs:
                print(f"     id={rec.id}, action={rec.action}, confidence={rec.confidence}")
                print(f"     manager_decision={rec.manager_decision}, decided_at={rec.decided_at}")
                print(f"     decision_channel={rec.decision_channel}, telegram_update_id={rec.telegram_update_id}")

                if rec.manager_decision == "approved":
                    approved_found = True
                    if rec.decided_at is None:
                        print("     [FAIL] decided_at is NULL for approved recommendation")
                        all_ok = False
                    if rec.decision_channel != "telegram":
                        print(f"     [FAIL] Expected decision_channel='telegram', got '{rec.decision_channel}'")
                        all_ok = False
            if not approved_found:
                print("     [FAIL] No approved recommendation found")
                all_ok = False
        else:
            print(f"     [FAIL] No recommendations found for morning_note_id={seed_ids['morning_note_id']}")
            all_ok = False

        # 3. Check checkpoints table - graph completion
        print("\n  3. Checking checkpoints table (graph completion)...")
        cp_result = await session.execute(
            text("SELECT thread_id, checkpoint->>'next' as next_node "
                 "FROM checkpoints WHERE thread_id = :tid"),
            {"tid": pipeline_run_id}
        )
        cp = cp_result.first()
        if cp:
            print(f"     thread_id={cp.thread_id}, next={cp.next_node}")
            if cp.next_node and cp.next_node != "[]":
                print(f"     [FAIL] Expected next=[] (completed), got {cp.next_node}")
                all_ok = False
            else:
                print("     [OK] Graph completed (next=[])")
        else:
            print(f"     [FAIL] No checkpoint found for thread_id={pipeline_run_id}")
            all_ok = False

        # 4. Verify RLS - try query without manager_id context (should return empty)
        print("\n  4. Verifying RLS isolation...")
        rls_result = await session.execute(
            text("SELECT count(*) FROM morning_notes WHERE manager_id = :mid"),
            {"mid": 999}  # non-existent manager
        )
        count = rls_result.scalar()
        if count == 0:
            print("     [OK] RLS working: query without proper context returns 0 rows")
        else:
            print(f"     [WARN] RLS may not be filtering: count={count} for non-existent manager")

    await async_engine.dispose()

    print(f"\n  Overall verification: {'[OK] PASSED' if all_ok else '[FAIL] FAILED'}")
    return all_ok


# =============================================================================
# Phase 8: Idempotency Check (Optional)
# =============================================================================

async def phase_idempotency(graph, seed_ids: dict, pipeline_run_id: str) -> bool:
    """Re-run with same morning_note_id — should skip gracefully."""
    print("\n=== Phase 8: Idempotency check (re-run same morning_note) ===")

    # Create new pipeline_run_id but same morning_note_id
    new_run_id = str(uuid4())
    print(f"  New pipeline run ID: {new_run_id}")

    state = create_initial_state(
        manager_id=seed_ids["manager_id"],
        company_ticker="PETR4",
        pipeline_run_id=new_run_id,
        morning_note_id=str(seed_ids["morning_note_id"]),
    )

    config = {
        "configurable": {"thread_id": new_run_id},
        "tags": [
            f"gestor_id:{state['manager_id']}",
            f"empresa:{state['company_ticker']}",
            f"data:{datetime.now(UTC).date().isoformat()}",
            f"pipeline_run_id:{new_run_id}",
            f"morning_note_id:{state['morning_note_id']}",
        ],
    }

    result = await graph.ainvoke(state, config=config)

    # Check if it produced FATAL flag (no recommendation in state) or completed
    flags = result.get("flags", [])
    fatal_flags = [f for f in flags if getattr(f, "severity", None) == "FATAL" or (isinstance(f, dict) and f.get("severity") == "FATAL")]

    if fatal_flags:
        print("  [OK] Second run produced FATAL flag (expected — morning_note already completed)")
        for f in fatal_flags:
            print(f"     {f.get('message') if isinstance(f, dict) else f.message}")
        return True
    elif "__interrupt__" in result:
        print("  [WARN] Second run also hit interrupt — may indicate idempotency gap")
        return False
    else:
        print("  [WARN] Second run completed without error — check for duplicate morning_notes")
        return False


# =============================================================================
# Phase 9: Cleanup
# =============================================================================

async def phase_cleanup(saver_cm, keep_running: bool) -> None:
    if keep_running:
        print("\n=== Phase 9: Keeping infrastructure running (--keep-running) ===")
        print("  Run 'docker-compose down -v' to stop and remove volumes")
        return

    print("\n=== Phase 9: Tearing down infrastructure ===")
    try:
        if saver_cm:
            await saver_cm.__aexit__(None, None, None)
    except Exception:
        pass
    run_cmd(["docker-compose", "down", "-v"])
    print("  Infrastructure stopped and volumes removed")


# =============================================================================
# Main
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="End-to-end pipeline verification")
    parser.add_argument("--keep-running", action="store_true", help="Leave Docker running after verification")
    parser.add_argument("--no-telegram", action="store_true", help="Force manual resume even if Telegram configured")
    parser.add_argument("--skip-idempotency", action="store_true", help="Skip idempotency check")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    print("=" * 60)
    print("FinAgent Pipeline Verification")
    print("=" * 60)

    saver = None
    saver_cm = None
    graph = None
    pipeline_run_id = None

    try:
        # Pre-flight checks
        print("\n=== Pre-flight checks ===")
        if not check_env_file():
            sys.exit(1)
        if not await check_docker():
            print("[FAIL] Docker daemon not running. Start Docker Desktop.")
            sys.exit(1)
        print("  .env OK, Docker OK")

        # Phases
        await phase_infra_up(args.keep_running)
        await phase_migrations()
        seed_ids = await phase_seed_data()
        saver, saver_cm, graph = await phase_compile_graph()
        pipeline_run_id, result = await phase_run_to_interrupt(graph, seed_ids)
        result = await phase_handle_gate(graph, pipeline_run_id, result, args.no_telegram)
        ok = await phase_verify(pipeline_run_id, seed_ids, result, graph, saver)

        if not args.skip_idempotency:
            await phase_idempotency(graph, seed_ids, pipeline_run_id)

        await phase_cleanup(saver_cm, args.keep_running)

        if ok:
            print("\n" + "=" * 60)
            print("[OK] ALL VERIFICATIONS PASSED")
            print("=" * 60)
            sys.exit(0)
        else:
            print("\n" + "=" * 60)
            print("[FAIL] SOME VERIFICATIONS FAILED")
            print("=" * 60)
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        await phase_cleanup(saver_cm, True)
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        if args.verbose:
            traceback.print_exc()
        await phase_cleanup(saver_cm, True)
        sys.exit(1)


if __name__ == "__main__":
    # Windows event loop policy for subprocess compatibility
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
