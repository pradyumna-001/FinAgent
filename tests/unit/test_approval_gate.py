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
