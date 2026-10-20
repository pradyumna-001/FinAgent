import pytest
from unittest.mock import patch

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

    def mock_interrupt(data):
        return "invalid_decision"

    with patch('app.agents.approval_gate.interrupt', side_effect=mock_interrupt):
        result = await approval_gate_node(state)
        assert "flags" in result
        assert len(result["flags"]) == 1
        assert result["flags"][0].source == "approval_gate_node"
        assert result["flags"][0].severity == Severity.FATAL
        assert "invalid manager decision" in result["flags"][0].message
        assert result["manager_decision"] is None
        assert result["decision_channel"] is None
        assert "data_freshness" in result
        assert "approval_gate" in result["data_freshness"]

    