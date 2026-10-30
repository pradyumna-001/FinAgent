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
        from app.agents.consolidate import consolidate_node
        from app.graph.state import create_initial_state_multi

        async with SessionLocal() as session:
            tickers_data = [
                ("PETR4", "Petrobras", "Energy"),
                ("VALE3", "Vale", "Materials"),
                ("ITUB4", "Itau", "Financial"),
            ]
            # Clean up in correct order: children first - delete ALL to avoid conflicts between tests
            await session.execute(delete(PortfolioHolding))
            await session.execute(delete(Portfolio))
            await session.execute(delete(Company))
            await session.execute(delete(Manager))
            await session.commit()

            # Insert companies with explicit IDs
            for i, (ticker, name, sector) in enumerate(tickers_data, start=1):
                await session.execute(insert(Company).values(id=i, ticker=ticker, name=name, sector=sector))

            # Insert test manager and portfolio
            await session.execute(insert(Manager).values(id=999, name="Test Manager", email="test@test.com", password_hash="hash"))
            await session.execute(insert(Portfolio).values(id=999, manager_id=999, name="Test Portfolio"))

            # Add portfolio holdings
            for i, (ticker, _, _) in enumerate(tickers_data, start=1):
                await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=i, weight=1.0/len(tickers_data)))

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
        from app.agents.consolidate import consolidate_node
        from app.graph.state import create_initial_state_multi

        async with SessionLocal() as session:
            tickers_data = [
                ("PETR4", "Petrobras", "Energy"),
                ("RECV3", "PetroReconcavo", "Energy"),
                ("PRIO3", "PetroRio", "Energy"),
                ("ITUB4", "Itau", "Financial"),
            ]
            # Clean up in correct order: children first - delete ALL to avoid conflicts between tests
            await session.execute(delete(PortfolioHolding))
            await session.execute(delete(Portfolio))
            await session.execute(delete(Company))
            await session.execute(delete(Manager))
            await session.commit()

            # Insert companies with explicit IDs
            for i, (ticker, name, sector) in enumerate(tickers_data, start=1):
                await session.execute(insert(Company).values(id=i, ticker=ticker, name=name, sector=sector))

            # Insert test manager and portfolio
            await session.execute(insert(Manager).values(id=999, name="Test Manager", email="test@test.com", password_hash="hash"))
            await session.execute(insert(Portfolio).values(id=999, manager_id=999, name="Test Portfolio"))

            # Add portfolio holdings
            for i, (ticker, _, _) in enumerate(tickers_data, start=1):
                await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=i, weight=1.0/len(tickers_data)))

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


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_no_concentration_flag_under_40():
    """No concentration flag when all sectors under 40%."""
    async def _test(SessionLocal):
        from app.agents.consolidate import consolidate_node
        from app.graph.state import create_initial_state_multi

        async with SessionLocal() as session:
            tickers_data = [
                ("PETR4", "Petrobras", "Energy"),
                ("VALE3", "Vale", "Materials"),
                ("ITUB4", "Itau", "Financial"),
                ("ABEV3", "Ambev", "Consumer"),
            ]
            # Clean up in correct order: children first - delete ALL to avoid conflicts between tests
            await session.execute(delete(PortfolioHolding))
            await session.execute(delete(Portfolio))
            await session.execute(delete(Company))
            await session.execute(delete(Manager))
            await session.commit()

            # Insert companies with explicit IDs
            for i, (ticker, name, sector) in enumerate(tickers_data, start=1):
                await session.execute(insert(Company).values(id=i, ticker=ticker, name=name, sector=sector))

            # Insert test manager and portfolio
            await session.execute(insert(Manager).values(id=999, name="Test Manager", email="test@test.com", password_hash="hash"))
            await session.execute(insert(Portfolio).values(id=999, manager_id=999, name="Test Portfolio"))

            # Add portfolio holdings
            for i, (ticker, _, _) in enumerate(tickers_data, start=1):
                await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=i, weight=1.0/len(tickers_data)))

            await session.commit()

        state = create_initial_state_multi(
            manager_id=999,
            company_tickers=["PETR4", "VALE3", "ITUB4", "ABEV3"],
            pipeline_run_id="test-run",
            morning_note_id="test-note"
        )

        result = await consolidate_node(state)

        assert "portfolio_risk_flags" in result
        assert len(result["portfolio_risk_flags"]) == 0

    await _run_test_with_engine(_test)


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_stale_data_flag():
    """Consolidate flags stale tickers (>24h old data)."""
    async def _test(SessionLocal):
        from datetime import UTC, datetime, timedelta

        from app.agents.consolidate import consolidate_node
        from app.graph.state import create_initial_state_multi

        async with SessionLocal() as session:
            tickers_data = [
                ("PETR4", "Petrobras", "Energy"),
                ("VALE3", "Vale", "Materials"),
            ]
            # Clean up in correct order: children first - delete ALL to avoid conflicts between tests
            await session.execute(delete(PortfolioHolding))
            await session.execute(delete(Portfolio))
            await session.execute(delete(Company))
            await session.execute(delete(Manager))
            await session.commit()

            # Insert companies with explicit IDs
            for i, (ticker, name, sector) in enumerate(tickers_data, start=1):
                await session.execute(insert(Company).values(id=i, ticker=ticker, name=name, sector=sector))

            # Insert test manager and portfolio
            await session.execute(insert(Manager).values(id=999, name="Test Manager", email="test@test.com", password_hash="hash"))
            await session.execute(insert(Portfolio).values(id=999, manager_id=999, name="Test Portfolio"))

            # Add portfolio holdings
            for i, (ticker, _, _) in enumerate(tickers_data, start=1):
                await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=i, weight=1.0/len(tickers_data)))

            await session.commit()

        state = create_initial_state_multi(
            manager_id=999,
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

    await _run_test_with_engine(_test)


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_no_stale_flag_when_all_fresh():
    """No stale data flag when all data is fresh."""
    async def _test(SessionLocal):
        from datetime import UTC, datetime, timedelta

        from app.agents.consolidate import consolidate_node
        from app.graph.state import create_initial_state_multi

        async with SessionLocal() as session:
            tickers_data = [
                ("PETR4", "Petrobras", "Energy"),
                ("VALE3", "Vale", "Materials"),
            ]
            # Clean up in correct order: children first - delete ALL to avoid conflicts between tests
            await session.execute(delete(PortfolioHolding))
            await session.execute(delete(Portfolio))
            await session.execute(delete(Company))
            await session.execute(delete(Manager))
            await session.commit()

            # Insert companies with explicit IDs
            for i, (ticker, name, sector) in enumerate(tickers_data, start=1):
                await session.execute(insert(Company).values(id=i, ticker=ticker, name=name, sector=sector))

            # Insert test manager and portfolio
            await session.execute(insert(Manager).values(id=999, name="Test Manager", email="test@test.com", password_hash="hash"))
            await session.execute(insert(Portfolio).values(id=999, manager_id=999, name="Test Portfolio"))

            # Add portfolio holdings
            for i, (ticker, _, _) in enumerate(tickers_data, start=1):
                await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=i, weight=1.0/len(tickers_data)))

            await session.commit()

        state = create_initial_state_multi(
            manager_id=999,
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

    await _run_test_with_engine(_test)


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_empty_tickers():
    """Consolidate handles empty tickers gracefully."""
    state = create_initial_state_multi(
        manager_id=999,
        company_tickers=[],
        pipeline_run_id="test-run",
        morning_note_id="test-note"
    )

    result = await consolidate_node(state)

    assert result["sector_weights"] == {}
    assert result["portfolio_risk_flags"] == []
    assert result["portfolio_data_flags"] == []
    assert "portfolio" in result["data_freshness"]


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_unknown_sector():
    """Consolidate handles unknown sectors."""
    async def _test(SessionLocal):
        from app.agents.consolidate import consolidate_node
        from app.graph.state import create_initial_state_multi

        async with SessionLocal() as session:
            tickers_data = [
                ("PETR4", "Petrobras", None),
            ]
            # Clean up in correct order: children first - delete ALL to avoid conflicts between tests
            await session.execute(delete(PortfolioHolding))
            await session.execute(delete(Portfolio))
            await session.execute(delete(Company))
            await session.execute(delete(Manager))
            await session.commit()

            # Insert companies with explicit IDs
            for i, (ticker, name, sector) in enumerate(tickers_data, start=1):
                await session.execute(insert(Company).values(id=i, ticker=ticker, name=name, sector=sector))

            # Insert test manager and portfolio
            await session.execute(insert(Manager).values(id=999, name="Test Manager", email="test@test.com", password_hash="hash"))
            await session.execute(insert(Portfolio).values(id=999, manager_id=999, name="Test Portfolio"))

            # Add portfolio holdings
            for i, (ticker, _, _) in enumerate(tickers_data, start=1):
                await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=i, weight=1.0/len(tickers_data)))

            await session.commit()

        state = create_initial_state_multi(
            manager_id=999,
            company_tickers=["PETR4"],
            pipeline_run_id="test-run",
            morning_note_id="test-note"
        )

        result = await consolidate_node(state)

        assert result["sector_weights"]["Unknown"] == 1.0

    await _run_test_with_engine(_test)
