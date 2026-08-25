import logging
from datetime import datetime
from unittest.mock import patch, AsyncMock

import pytest

from app.agents.company import company_agent_node
from app.graph.state import create_initial_state, DataFlag
from app.services.tavily import TavilyArticle, TavilyResult
from app.utils.flags import Severity


def make_state():
    return create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run",
        morning_note_id="note"
    )


def _tavily_result(articles=None, error=None):
    return TavilyResult(articles=articles or [], error=error)


@pytest.mark.asyncio
async def test_company_agent_no_key():
    from app.services.tavily import TavilyConfigError
    with patch("app.agents.company.TavilyService", side_effect=TavilyConfigError("TAVILY_API_KEY missing or empty")):
        state = make_state()
        result = await company_agent_node(state)

    assert result["company_events"] == []
    flag = result["flags"][-1]
    assert isinstance(flag, DataFlag)
    assert flag.source == "tavily"
    assert flag.severity == Severity.FATAL
    assert isinstance(result["data_freshness"]["company"], datetime)


@pytest.mark.asyncio
async def test_company_agent_llm_none():
    article = TavilyArticle(
        title="PETR4 earnings Q3",
        content="Petrobras reported record earnings...",
        url="https://infomoney.com.br/petr4",
    )
    result = _tavily_result(articles=[article])

    with patch("app.agents.company.TavilyService") as MockService:
        MockService.return_value.search = AsyncMock(return_value=result)
        with patch("app.agents.company.summarize", new=AsyncMock(return_value=None)):
            state = make_state()
            res = await company_agent_node(state)

    events = res["company_events"]
    assert len(events) == 1
    assert events[0]["summary"] == "Petrobras reported record earnings..."
    flag = res["flags"][-1]
    assert isinstance(flag, DataFlag)
    assert flag.source == "nvidia_nim"


@pytest.mark.asyncio
async def test_company_agent_happy_path():
    article = TavilyArticle(
        title="PETR4 earnings Q3",
        content="Petrobras reported record earnings...",
        url="https://infomoney.com.br/petr4",
    )
    result = _tavily_result(articles=[article])

    with patch("app.agents.company.TavilyService") as MockService:
        MockService.return_value.search = AsyncMock(return_value=result)
        with patch("app.agents.company.summarize", new=AsyncMock(return_value="Resumo de earnings da Petrobras.")):
            state = make_state()
            res = await company_agent_node(state)

    events = res["company_events"]
    assert len(events) == 1
    assert events[0]["title"] == "PETR4 earnings Q3"
    assert events[0]["summary"] == "Resumo de earnings da Petrobras."
    assert events[0]["source"] == "https://infomoney.com.br/petr4"
    assert isinstance(res["data_freshness"]["company"], datetime)
    assert res["flags"] == []


@pytest.mark.asyncio
async def test_company_agent_tavily_service_error():
    error = DataFlag(source="tavily", severity=Severity.WARNING, message="Tavily request error: network down")
    result = _tavily_result(error=error)

    with patch("app.agents.company.TavilyService") as MockService:
        MockService.return_value.search = AsyncMock(return_value=result)
        state = make_state()
        res = await company_agent_node(state)

    assert res["company_events"] == []
    flag = res["flags"][-1]
    assert isinstance(flag, DataFlag)
    assert flag.source == "tavily"
    assert flag.severity == Severity.WARNING


@pytest.mark.asyncio
async def test_company_agent_logs_entry(caplog):
    with caplog.at_level(logging.INFO, logger="app.agents.company"):
        with patch("app.agents.company.TavilyService") as MockService:
            MockService.return_value.search = AsyncMock(return_value=_tavily_result())
            await company_agent_node(make_state())
    records = [r for r in caplog.records if r.name == "app.agents.company"]
    assert len(records) >= 1
    rec = records[0]
    assert rec.pipeline_run_id == "run"
    assert rec.morning_note_id == "note"
    assert rec.manager_id == 1
