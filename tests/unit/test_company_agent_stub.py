"""Stub tests covering the agent-side propagation of TavilyService errors
that originate from bad response shapes (the contract handoff from the
old inline parse-block guard to the new service-level guard).
"""
import pytest
from unittest.mock import patch, AsyncMock

from app.agents.company import company_agent_node
from app.graph.state import create_initial_state, DataFlag
from app.services.tavily import TavilyResult
from app.utils.flags import Severity


def make_state():
    return create_initial_state(
        manager_id=1, company_ticker="PETR4",
        pipeline_run_id="run", morning_note_id="note",
    )


@pytest.mark.asyncio
async def test_company_agent_propagates_service_fatal_for_null_fields():
    """Service detects null title/content and returns a FATAL DataFlag.
    The agent must propagate it (not swallow, not re-validate), set
    company_events to empty, and return early.
    """
    error = DataFlag(
        source="tavily",
        severity=Severity.FATAL,
        message="Tavily returned articles with null title/content for query 'PETR4 news Brazil' - schema may have changed",
    )
    result = TavilyResult(articles=[], error=error)

    with patch("app.agents.company.TavilyService") as MockService:
        MockService.return_value.search = AsyncMock(return_value=result)
        state = make_state()
        res = await company_agent_node(state)

    assert res["company_events"] == []
    assert len(res["flags"]) == 1
    flag = res["flags"][0]
    assert isinstance(flag, DataFlag)
    assert flag.source == "tavily"
    assert flag.severity == Severity.FATAL
    assert "PETR4 news Brazil" in flag.message
