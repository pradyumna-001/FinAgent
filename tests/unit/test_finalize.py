"""Unit tests for finalize_morning_note_node (multi-ticker)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.finalize import finalize_morning_note_node
from app.graph.state import create_initial_state_multi


@pytest.mark.asyncio
async def test_finalize_skips_on_rejected() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4"],
        pipeline_run_id="run-1",
        morning_note_id="1",
    )
    state["manager_decision"] = "rejected"
    result = await finalize_morning_note_node(state)
    assert result.get("flags", []) == []
    assert "data_freshness" in result
    assert "finalize" in result["data_freshness"]


@pytest.mark.asyncio
async def test_finalize_skips_on_partial() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4"],
        pipeline_run_id="run-1",
        morning_note_id="1",
    )
    state["manager_decision"] = "partial"
    result = await finalize_morning_note_node(state)
    assert result.get("flags", []) == []
    assert "data_freshness" in result
    assert "finalize" in result["data_freshness"]


@pytest.mark.asyncio
async def test_finalize_skips_on_none() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4"],
        pipeline_run_id="run-1",
        morning_note_id="1",
    )
    state["manager_decision"] = None
    result = await finalize_morning_note_node(state)
    assert result.get("flags", []) == []
    assert "data_freshness" in result
    assert "finalize" in result["data_freshness"]


@pytest.mark.asyncio
async def test_finalize_missing_morning_note_id() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4"],
        pipeline_run_id="run-1",
        morning_note_id="1",
    )
    state["manager_decision"] = "approved"
    state["morning_note_id"] = None  # type: ignore[typeddict-item]
    result = await finalize_morning_note_node(state)
    assert result.get("flags", []) == []
    assert "data_freshness" in result
    assert "finalize" in result["data_freshness"]


@pytest.mark.asyncio
async def test_finalize_success() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4"],
        pipeline_run_id="run-1",
        morning_note_id="1",
    )
    state["manager_decision"] = "approved"

    with patch("app.agents.finalize.SessionLocal") as mock_session_class:
        mock_session = AsyncMock()
        mock_txn = AsyncMock()
        mock_txn.__aenter__ = AsyncMock(return_value=mock_session)
        mock_txn.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin = lambda: mock_txn
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()

        result = await finalize_morning_note_node(state)

    assert result["flags"] == []
    assert "data_freshness" in result
    assert "finalize" in result["data_freshness"]
    mock_session.execute.assert_called()
