"""Integration tests for Consolidate node using existing PostgreSQL.

Each test creates its own isolated engine and session to avoid event loop conflicts.
"""

import pytest
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.session as db_session
from app.agents.consolidate import consolidate_node
from app.db.models import Company, Manager, Portfolio, PortfolioHolding
from app.graph.state import create_initial_state_multi

DB_URL = "postgresql+asyncpg://finagent:password@localhost:5434/finagent"


async def _run_test_with_engine(test_func):
    """Run a test with its own engine, ensuring proper cleanup in the same event loop."""
    engine = create_async_engine(
        "postgresql+asyncpg://finagent:password@localhost:5434/finagent",
        echo=False,
        pool_pre_ping=True,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    # Patch the global SessionLocal for this test
    original_session_local = db_session.SessionLocal
    db_session.SessionLocal = SessionLocal

    try:
        await test_func(SessionLocal)
    finally:
        db_session.SessionLocal = original_session_local
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_computes_sector_weights():
    """Consolidate computes sector weights from Company sectors."""
    async def _test(SessionLocal):

        # Clean up any existing test data - delete in correct order: children first
        async with SessionLocal() as session:
            await session.execute(delete(PortfolioHolding))
            await session.execute(delete(Portfolio))
            await session.execute(delete(Company))
            await session.execute(delete(Manager))
            await session.commit()

            # Insert companies with explicit IDs
            await session.execute(insert(Company).values(id=1, ticker="PETR4", name="Petrobras", sector="Energy"))
            await session.execute(insert(Company).values(id=2, ticker="VALE3", name="Vale", sector="Materials"))
            await session.execute(insert(Company).values(id=3, ticker="ITUB4", name="Itau", sector="Financial"))

            # Insert test manager and portfolio
            await session.execute(insert(Manager).values(id=999, name="Test Manager", email="test@test.com", password_hash="hash"))
            await session.execute(insert(Portfolio).values(id=999, manager_id=999, name="Test Portfolio"))

            # Add portfolio holdings
            await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=1, weight=1/3))
            await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=2, weight=1/3))
            await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=3, weight=1/3))

            await session.commit()


        state = create_initial_state_multi(
            manager_id=999,
            company_tickers=["PETR4", "VALE3", "ITUB4"],
            pipeline_run_id="test-run",
            morning_note_id="test-note"
        )

        result = await consolidate_node(state)

        assert "sector_weights" in result
        assert result["sector_weights"]["Energy"] == pytest.approx(1/3)
        assert result["sector_weights"]["Materials"] == pytest.approx(1/3)
        assert result["sector_weights"]["Financial"] == pytest.approx(1/3)
        assert abs(sum(result["sector_weights"].values()) - 1.0) < 0.01

    await _run_test_with_engine(_test)


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_sector_concentration_flag():
    """Consolidate flags sector concentration > 40%."""
    async def _test(SessionLocal):

        async with SessionLocal() as session:
            # Clean up any existing data - delete in correct order: children first
            await session.execute(delete(PortfolioHolding))
            await session.execute(delete(Portfolio))
            await session.execute(delete(Company))
            await session.execute(delete(Manager))
            await session.commit()

            # Insert companies with explicit IDs
            await session.execute(insert(Company).values(id=1, ticker="PETR4", name="Petrobras", sector="Energy"))
            await session.execute(insert(Company).values(id=2, ticker="RECV3", name="PetroReconcavo", sector="Energy"))
            await session.execute(insert(Company).values(id=3, ticker="PRIO3", name="PetroRio", sector="Energy"))
            await session.execute(insert(Company).values(id=4, ticker="ITUB4", name="Itau", sector="Financial"))

            # Insert test manager and portfolio
            await session.execute(insert(Manager).values(id=999, name="Test Manager", email="test@test.com", password_hash="hash"))
            await session.execute(insert(Portfolio).values(id=999, manager_id=999, name="Test Portfolio"))

            # Add portfolio holdings
            await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=1, weight=0.25))
            await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=2, weight=0.25))
            await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=3, weight=0.25))
            await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=4, weight=0.25))

            await session.commit()


        state = create_initial_state_multi(
            manager_id=999,
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

    await _run_test_with_engine(_test)
