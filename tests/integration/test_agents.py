import pytest
from unittest.mock import patch, AsyncMock

from app.agents.macro import macro_agent_node
from app.agents.company import company_agent_node
from app.agents.quant import quant_agent_node
from app.graph.state import create_initial_state, DataFlag
from app.services.tavily import TavilyResult
from app.services.yfinance import YfinanceResult
from app.utils.flags import Severity


def make_state():
    return create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-1",
        morning_note_id="note-1"
    )


@pytest.mark.asyncio
async def test_pipeline_all_agents_fail_shares_state():
    """Sequential A1: macro -> company -> quant, all mocked to fail,
    against one shared AgentState. Flags accumulate; freshness keys
    land per agent; state stays internally consistent."""
    state = make_state()

    err = DataFlag(source="tavily", severity=Severity.WARNING, message="Tavily 500")
    with patch("app.agents.macro.TavilyService") as M, \
         patch("app.agents.macro.summarize", new=AsyncMock(return_value="")):
        M.return_value.search = AsyncMock(return_value=TavilyResult(articles=[], error=err))
        state = await macro_agent_node(state)
    assert state["macro_context"] is None
    assert len(state["flags"]) == 1
    assert "macro" in state["data_freshness"]

    with patch("app.agents.company.TavilyService") as C, \
         patch("app.agents.company.summarize", new=AsyncMock(return_value="")):
        C.return_value.search = AsyncMock(return_value=TavilyResult(articles=[], error=err))
        state = await company_agent_node(state)
    assert state["company_events"] == []
    assert len(state["flags"]) == 2
    assert "company" in state["data_freshness"]

    stale_err = DataFlag(
        source="yfinance",
        severity=Severity.FATAL,
        message="Yfinance data 'PETR4' is 48.0h old (max 24h)"
    )
    with patch("app.agents.quant.YfinanceService") as Q:
        Q.return_value.search = AsyncMock(return_value=YfinanceResult(metrics=None, error=stale_err))
        state = await quant_agent_node(state)
    assert state["quant_metrics"] is None
    assert state["flags"][-1].source == "yfinance"
    assert "48" in state["flags"][-1].message
    assert state["data_freshness"]["quant"] is not None

    assert len(state["flags"]) == 3
    assert set(state["data_freshness"]) == {"macro", "company", "quant"}
    assert state["manager_id"] == 1
    assert state["company_ticker"] == "PETR4"
    