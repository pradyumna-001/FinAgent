import pytest
from unittest.mock import patch

from app.agents.risk import risk_agent_node
from app.graph.state import create_initial_state
from app.utils.flags import DataFlag, Severity


def make_state():
    return create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-1",
        morning_note_id="note-1",
    )


@pytest.mark.asyncio
async def test_risk_agent_happy_path() -> None:
    """mock summarize returning valid JSON; assert risk_flags populated"""
    with patch("app.agents.risk.summarize") as MockSummarize:
        MockSummarize.return_value = (
            '[{"probability": 0.7, "impact": "high", '
            '"description": "Market crash risk", "severity": "warning"}]'
        )
        state = await risk_agent_node(make_state())
        assert len(state["risk_flags"]) >= 1
        rf = state["risk_flags"][0]
        assert rf["probability"] == 0.7
        assert rf["impact"] == "high"
        assert rf["description"] == "Market crash risk"
        assert rf["severity"] == "warning"
        assert state["data_freshness"]["risk"] is not None


@pytest.mark.asyncio
async def test_risk_agent_no_raw_text_dataflag() -> None:
    """mock summarize returning None; assert DataFlag appended"""
    with patch("app.agents.risk.summarize", return_value=None):
        state = await risk_agent_node(make_state())
        assert len(state["flags"]) >= 1
        assert state["flags"][-1].source == "risk_parse"
        assert state["flags"][-1].severity == Severity.WARNING
        assert "risk flag(s) dropped" in state["flags"][-1].message
        assert len(state["risk_flags"]) == 0