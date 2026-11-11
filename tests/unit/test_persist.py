"""Unit tests for persist_recommendation_node (multi-ticker)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.persist import persist_recommendation_node
from app.graph.state import create_initial_state_multi
from app.utils.flags import Severity


@pytest.mark.asyncio
async def test_persist_node_no_tickers() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=[],
        pipeline_run_id="run-1",
        morning_note_id="note-1",
    )
    result = await persist_recommendation_node(state)

    assert result["flags"][0].severity == Severity.FATAL
    assert "no company_tickers" in result["flags"][0].message
    assert "data_freshness" in result
    assert "persist" in result["data_freshness"]


@pytest.mark.asyncio
async def test_persist_node_no_recommendations() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["AAPL", "GOOG"],
        pipeline_run_id="run-1",
        morning_note_id="note-1",
    )
    state["recommendations"] = {}
    result = await persist_recommendation_node(state)

    assert result["flags"][0].severity == Severity.FATAL
    assert "no recommendations" in result["flags"][0].message
    assert "data_freshness" in result
    assert "persist" in result["data_freshness"]


@pytest.mark.asyncio
async def test_persist_node_multi_ticker_success() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4", "VALE3"],
        pipeline_run_id="run-1",
        morning_note_id="1",
    )
    state["recommendations"] = {
        "PETR4": {"action": "buy", "confidence": 0.9, "justification": "Strong fundamentals"},
        "VALE3": {"action": "sell", "confidence": 0.8, "justification": "Weak market conditions"},
    }
    state["confidence_scores"] = {
        "PETR4": {"persist": 0.95},
        "VALE3": {"persist": 0.85},
    }

    captured_recs = []
    with patch("app.agents.persist.SessionLocal") as mock_session_class:
        mock_session = AsyncMock()

        # Create async context manager for session.begin()
        mock_txn = AsyncMock()
        mock_txn.__aenter__ = AsyncMock(return_value=mock_session)
        mock_txn.__aexit__ = AsyncMock(return_value=None)
        # begin() returns the async context manager directly (not a coroutine)
        mock_session.begin = lambda: mock_txn

        # SessionLocal() returns async context manager yielding mock_session
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

        def capture_add(obj):
            captured_recs.append(obj)

        mock_session.add = MagicMock(side_effect=capture_add)
        async def mock_flush():
            for i, rec in enumerate(captured_recs):
                rec.id = i + 100

        mock_session.flush = AsyncMock(side_effect=mock_flush)
        mock_session.execute = AsyncMock()
        result = await persist_recommendation_node(state)

        assert "recommendation_id" in result
        assert isinstance(result["recommendation_id"], dict)
        assert "PETR4" in result["recommendation_id"]
        assert "VALE3" in result["recommendation_id"]
        assert isinstance(result["recommendation_id"]["PETR4"], int)
        assert isinstance(result["recommendation_id"]["VALE3"], int)
        assert len(result["flags"]) == 0

