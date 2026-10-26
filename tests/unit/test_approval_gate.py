from unittest.mock import patch

import pytest

from app.agents.approval_gate import approval_gate_node
from app.graph.state import create_initial_state
from app.utils.flags import Severity


@pytest.mark.asyncio
async def test_approval_gate_node_no_recommendation() -> None:
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-1",
        morning_note_id="note-1"
    )

    result = await approval_gate_node(state)
    assert "flags" in result
    assert len(result["flags"]) == 1
    assert result["flags"][0].source == "approval_gate_node"
    assert result["flags"][0].severity == Severity.FATAL
    assert "no recommendation in current state" in result["flags"][0].message
    assert "data_freshness" in result
    assert "approval_gate" in result["data_freshness"]
    assert not ("manager_decision" in result or "decision_channel" in result)


@pytest.mark.asyncio
async def test_approval_gate_node_invalid_decision() -> None:
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-1",
        morning_note_id="note-1"
    )
    state["recommendation_id"] = 123
    state["recommendation"] = {
        "action": "buy",
        "confidence": 0.9,
        "justification": "Strong fundamentals"
    }

    with patch("app.agents.approval_gate.interrupt") as mock_interrupt:
        mock_interrupt.return_value = "invalid_decision"
        result = await approval_gate_node(state)
        payload = mock_interrupt.call_args[0][0]

        assert payload["recommendation_id"] == 123
        assert payload["action"] == "buy"
        assert payload["ticker"] == "PETR4"
        assert payload["confidence"] == 0.9
        assert payload["justification"] == "Strong fundamentals"

        assert "flags" in result
        assert len(result["flags"]) == 1
        assert result["flags"][0].source == "approval_gate_node"
        assert result["flags"][0].severity == Severity.FATAL
        assert "invalid manager decision" in result["flags"][0].message
        assert result["manager_decision"] is None
        assert result["decision_channel"] is None
        assert "data_freshness" in result
        assert "approval_gate" in result["data_freshness"]


@pytest.mark.asyncio
async def test_approval_gate_node_valid_decision() -> None:
    state = create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-1",
        morning_note_id="note-1"
    )
    state["recommendation_id"] = 123
    state["recommendation"] = {
        "action": "buy",
        "confidence": 0.9,
        "justification": "Strong fundamentals"
    }

    with patch("app.agents.approval_gate.interrupt") as mock_interrupt, \
        patch("app.agents.approval_gate.session_write_decision") as mock_write:

        mock_interrupt.return_value = "approved"
        mock_write.return_value = None
        result = await approval_gate_node(state)

        mock_interrupt.assert_called_once()
        payload = mock_interrupt.call_args[0][0]
        assert payload["recommendation_id"] == 123
        assert payload["ticker"] == "PETR4"
        assert payload["action"] == "buy"
        assert payload["confidence"] == 0.9
        assert payload["justification"] == "Strong fundamentals"

        assert result["manager_decision"] == "approved"
        assert result["decision_channel"] == "telegram"
        assert "flags" in result
        assert len(result["flags"]) == 0
        assert "data_freshness" in result
        assert "approval_gate" in result["data_freshness"]
