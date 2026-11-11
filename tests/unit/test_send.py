"""Unit tests for send_note_node (multi-ticker)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.send import send_note_node
from app.graph.state import create_initial_state_multi
from app.utils.flags import Severity


@pytest.mark.asyncio
async def test_send_node_no_tickers() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=[],
        pipeline_run_id="run-1",
        morning_note_id="1",
    )
    result = await send_note_node(state)
    assert result["flags"][0].severity == Severity.FATAL
    assert "no company_tickers" in result["flags"][0].message
    assert "data_freshness" in result
    assert "send" in result["data_freshness"]


@pytest.mark.asyncio
async def test_send_node_no_recommendations() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4"],
        pipeline_run_id="run-1",
        morning_note_id="1",
    )
    state["recommendations"] = {}
    result = await send_note_node(state)
    assert result["flags"][0].severity == Severity.FATAL
    assert "no recommendations" in result["flags"][0].message
    assert "data_freshness" in result
    assert "send" in result["data_freshness"]


@pytest.mark.asyncio
async def test_send_node_multi_ticker_success() -> None:
    state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4", "VALE3"],
        pipeline_run_id="run-1",
        morning_note_id="1",
    )
    state["recommendations"] = {
        "PETR4": {"action": "buy", "confidence": 0.9, "justification": "Strong"},
        "VALE3": {"action": "sell", "confidence": 0.7, "justification": "Weak"},
    }
    state["recommendation_id"] = {"PETR4": 100, "VALE3": 101}
    state["confidence_scores"] = {
        "PETR4": {"send": 0.95},
        "VALE3": {"send": 0.85},
    }

    with patch("app.agents.send.build_telegram_channel") as mock_build:
        mock_channel = AsyncMock()
        mock_channel.send_note = AsyncMock()
        mock_build.return_value = mock_channel

        result = await send_note_node(state)

    assert result["decision_channel"] == "telegram"
    assert len(result["flags"]) == 0
    assert mock_channel.send_note.call_count == 2
    # Verify NotePayload was called with correct per-ticker rec_ids
    calls = mock_channel.send_note.call_args_list
    assert calls[0][0][0].recommendation_id == 100
    assert calls[0][0][0].ticker == "PETR4"
    assert calls[1][0][0].recommendation_id == 101
    assert calls[1][0][0].ticker == "VALE3"
