#!/usr/bin/env python
"""Standalone test runner for Consolidate node using existing PostgreSQL."""

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Set environment variables before importing app modules
os.environ["MIGRATION_DATABASE_URL"] = "postgresql+psycopg://finagent:password@localhost:5434/finagent"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://finagent:password@localhost:5434/finagent"

from sqlalchemy import delete, insert

from app.agents.consolidate import consolidate_node
from app.db.models import Company
from app.db.session import SessionLocal
from app.graph.state import create_initial_state_multi


async def test_consolidate_computes_sector_weights():
    """Consolidate computes sector weights from Company sectors."""
    print("Testing: test_consolidate_computes_sector_weights")
    async with SessionLocal() as session:
        await session.execute(delete(Company).where(Company.ticker.in_(["PETR4", "VALE3", "ITUB4"])))
        await session.execute(insert(Company).values(ticker="PETR4", name="Petrobras", sector="Energy"))
        await session.execute(insert(Company).values(ticker="VALE3", name="Vale", sector="Materials"))
        await session.execute(insert(Company).values(ticker="ITUB4", name="Itau", sector="Financial"))
        await session.commit()

    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4", "VALE3", "ITUB4"],
        pipeline_run_id="test-run",
        morning_note_id="test-note"
    )

    result = await consolidate_node(state)

    assert "sector_weights" in result
    assert result["sector_weights"]["Energy"] == 1/3
    assert result["sector_weights"]["Materials"] == 1/3
    assert result["sector_weights"]["Financial"] == 1/3
    assert abs(sum(result["sector_weights"].values()) - 1.0) < 0.01
    print("  PASSED")


async def test_consolidate_sector_concentration_flag():
    """Consolidate flags sector concentration > 40%."""
    print("Testing: test_consolidate_sector_concentration_flag")
    async with SessionLocal() as session:
        await session.execute(delete(Company).where(Company.ticker.in_(["PETR4", "RECV3", "PRIO3", "ITUB4"])))
        await session.execute(insert(Company).values(ticker="PETR4", name="Petrobras", sector="Energy"))
        await session.execute(insert(Company).values(ticker="RECV3", name="PetroReconcavo", sector="Energy"))
        await session.execute(insert(Company).values(ticker="PRIO3", name="PetroRio", sector="Energy"))
        await session.execute(insert(Company).values(ticker="ITUB4", name="Itau", sector="Financial"))
        await session.commit()

    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4", "RECV3", "PRIO3", "ITUB4"],
        pipeline_run_id="test-run",
        morning_note_id="test-note"
    )

    result = await consolidate_node(state)

    assert "portfolio_risk_flags" in result
    energy_flags = [f for f in result["portfolio_risk_flags"] if "Energy" in f["description"]]
    assert len(energy_flags) == 1
    assert energy_flags[0]["severity"] == "WARNING"
    assert energy_flags[0]["probability"] == 0.8
    print("  PASSED")


async def test_consolidate_no_concentration_flag_under_40():
    """No concentration flag when all sectors under 40%."""
    print("Testing: test_consolidate_no_concentration_flag_under_40")
    async with SessionLocal() as session:
        await session.execute(delete(Company).where(Company.ticker.in_(["PETR4", "VALE3", "ITUB4", "ABEV3"])))
        await session.execute(insert(Company).values(ticker="PETR4", name="Petrobras", sector="Energy"))
        await session.execute(insert(Company).values(ticker="VALE3", name="Vale", sector="Materials"))
        await session.execute(insert(Company).values(ticker="ITUB4", name="Itau", sector="Financial"))
        await session.execute(insert(Company).values(ticker="ABEV3", name="Ambev", sector="Consumer"))
        await session.commit()

    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4", "VALE3", "ITUB4", "ABEV3"],
        pipeline_run_id="test-run",
        morning_note_id="test-note"
    )

    result = await consolidate_node(state)

    assert "portfolio_risk_flags" in result
    assert len(result["portfolio_risk_flags"]) == 0
    print("  PASSED")


async def test_consolidate_stale_data_flag():
    """Consolidate flags stale tickers (>24h old data)."""
    print("Testing: test_consolidate_stale_data_flag")
    async with SessionLocal() as session:
        await session.execute(delete(Company).where(Company.ticker.in_(["PETR4", "VALE3"])))
        await session.execute(insert(Company).values(ticker="PETR4", name="Petrobras", sector="Energy"))
        await session.execute(insert(Company).values(ticker="VALE3", name="Vale", sector="Materials"))
        await session.commit()

    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4", "VALE3"],
        pipeline_run_id="test-run",
        morning_note_id="test-note"
    )

    now = datetime.now(UTC)
    stale_time = now - timedelta(hours=48)
    state["data_freshness"] = {
        "PETR4": now - timedelta(hours=2),
        "VALE3": stale_time,
        "macro": now
    }

    result = await consolidate_node(state)

    assert "portfolio_data_flags" in result
    stale_flags = [f for f in result["portfolio_data_flags"] if "stale" in f.message]
    assert len(stale_flags) == 1
    assert "1/2" in stale_flags[0].message
    print("  PASSED")


async def test_consolidate_no_stale_flag_when_all_fresh():
    """No stale data flag when all data is fresh."""
    print("Testing: test_consolidate_no_stale_flag_when_all_fresh")
    async with SessionLocal() as session:
        await session.execute(delete(Company).where(Company.ticker.in_(["PETR4", "VALE3"])))
        await session.execute(insert(Company).values(ticker="PETR4", name="Petrobras", sector="Energy"))
        await session.execute(insert(Company).values(ticker="VALE3", name="Vale", sector="Materials"))
        await session.commit()

    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4", "VALE3"],
        pipeline_run_id="test-run",
        morning_note_id="test-note"
    )

    now = datetime.now(UTC)
    state["data_freshness"] = {
        "PETR4": now - timedelta(hours=2),
        "VALE3": now - timedelta(hours=1),
        "macro": now
    }

    result = await consolidate_node(state)

    stale_flags = [f for f in result.get("portfolio_data_flags", []) if "stale" in f.message]
    assert len(stale_flags) == 0
    print("  PASSED")


async def test_consolidate_empty_tickers():
    """Consolidate handles empty tickers gracefully."""
    print("Testing: test_consolidate_empty_tickers")
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=[],
        pipeline_run_id="test-run",
        morning_note_id="test-note"
    )

    result = await consolidate_node(state)

    assert result["sector_weights"] == {}
    assert result["portfolio_risk_flags"] == []
    assert result["portfolio_data_flags"] == []
    assert "portfolio" in result["data_freshness"]
    print("  PASSED")


async def test_consolidate_unknown_sector():
    """Consolidate handles unknown sectors."""
    print("Testing: test_consolidate_unknown_sector")
    async with SessionLocal() as session:
        await session.execute(delete(Company).where(Company.ticker.in_(["PETR4"])))
        await session.execute(insert(Company).values(ticker="PETR4", name="Petrobras", sector=None))
        await session.commit()

    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4"],
        pipeline_run_id="test-run",
        morning_note_id="test-note"
    )

    result = await consolidate_node(state)

    assert result["sector_weights"]["Unknown"] == 1.0
    print("  PASSED")


async def main():
    print("Running Consolidate node tests against existing PostgreSQL container...")
    print("=" * 60)

    tests = [
        test_consolidate_computes_sector_weights,
        test_consolidate_sector_concentration_flag,
        test_consolidate_no_concentration_flag_under_40,
        test_consolidate_stale_data_flag,
        test_consolidate_no_stale_flag_when_all_fresh,
        test_consolidate_empty_tickers,
        test_consolidate_unknown_sector,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
