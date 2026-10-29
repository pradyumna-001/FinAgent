"""Integration tests for Consolidate node using existing PostgreSQL."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert

from app.agents.consolidate import consolidate_node
from app.db.models import Company
from app.db.session import SessionLocal
from app.graph.state import create_initial_state_multi


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_computes_sector_weights():
    """Consolidate computes sector weights from Company sectors."""
    async with SessionLocal() as session:
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
    assert result["sector_weights"]["Energy"] == pytest.approx(1/3)
    assert result["sector_weights"]["Materials"] == pytest.approx(1/3)
    assert result["sector_weights"]["Financial"] == pytest.approx(1/3)
    assert abs(sum(result["sector_weights"].values()) - 1.0) < 0.01


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_sector_concentration_flag():
    """Consolidate flags sector concentration > 40%."""
    async with SessionLocal() as session:
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


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_no_concentration_flag_under_40():
    """No concentration flag when all sectors under 40%."""
    async with SessionLocal() as session:
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


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_stale_data_flag():
    """Consolidate flags stale tickers (>24h old data)."""
    async with SessionLocal() as session:
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


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_no_stale_flag_when_all_fresh():
    """No stale data flag when all data is fresh."""
    async with SessionLocal() as session:
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


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_empty_tickers():
    """Consolidate handles empty tickers gracefully."""
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


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_unknown_sector():
    """Consolidate handles unknown sectors."""
    async with SessionLocal() as session:
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
