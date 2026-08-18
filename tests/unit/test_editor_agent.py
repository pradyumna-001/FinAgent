import pytest
from unittest.mock import patch

from app.agents.editor import editor_agent_node
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
async def test_editor_agent_happy_path() -> None:
    """mock summarize_nemotron returning valid JSON; assert morning_note, recommendation, confidence_scores populated"""
    with patch("app.agents.editor.summarize_nemotron") as MockSummarize:
        MockSummarize.return_value = (
            '{"morning_note": "Bom dia, mercado estável.", '
            '"recommendation": {"action": "keep", "justification": "Neutro", "confidence": 0.7}, '
            '"confidence_scores": {"macro": 0.8, "company": 0.7, "quant": 0.9, "risk": 0.6, "overall": 0.75}}'
        )
        state = await editor_agent_node(make_state())
        assert state["morning_note"] == "Bom dia, mercado estável."
        assert state["recommendation"]["action"] == "keep"
        assert state["confidence_scores"]["overall"] == 0.75
        assert state["data_freshness"]["editor"] is not None


@pytest.mark.asyncio
async def test_editor_agent_no_raw_text_dataflag() -> None:
    """mock summarize_nemotron returning None; assert DataFlag(FATAL) appended"""
    with patch("app.agents.editor.summarize_nemotron", return_value=None):
        state = await editor_agent_node(make_state())
        assert len(state["flags"]) >= 1
        assert state["flags"][-1].source == "summarize_nemotron"
        assert state["flags"][-1].severity == Severity.FATAL
        assert state["morning_note"] is None
        assert state["confidence_scores"] == {}


@pytest.mark.asyncio
async def test_editor_agent_invalid_json_dataflag() -> None:
    """mock summarize_nemotron returning invalid JSON; assert DataFlag(WARNING) appended"""
    with patch("app.agents.editor.summarize_nemotron", return_value="not valid json"):
        state = await editor_agent_node(make_state())
        assert len(state["flags"]) >= 1
        assert state["flags"][-1].source == "editor_parse"
        assert state["flags"][-1].severity == Severity.WARNING
        assert state["morning_note"] is None


@pytest.mark.asyncio
async def test_editor_agent_confidence_penalties_applied() -> None:
    """mock summarize_nemotron returning valid JSON; state has tavily flag; assert confidence penalized"""
    with patch("app.agents.editor.summarize_nemotron") as MockSummarize:
        MockSummarize.return_value = (
            '{"morning_note": "Bom dia.", '
            '"recommendation": {"action": "buy", "justification": "Forte", "confidence": 0.8}, '
            '"confidence_scores": {"macro": 0.9, "company": 0.8, "quant": 0.7, "risk": 0.6, "overall": 0.75}}'
        )
        state = make_state()
        state["flags"].append(
            DataFlag(
                source="tavily",
                severity=Severity.WARNING,
                message="tavily 500"
            )
        )
        state = await editor_agent_node(state)
        assert state["confidence_scores"]["macro"] == 0.49
        assert state["confidence_scores"]["company"] == 0.49
        assert "Aviso" in state["morning_note"]
        