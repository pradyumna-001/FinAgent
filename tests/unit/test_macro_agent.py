import logging
from datetime import datetime
from unittest.mock import patch, AsyncMock

import pytest

from app.agents.macro import macro_agent_node
from app.graph.state import create_initial_state, DataFlag
from app.services.tavily import TavilyArticle, TavilyResult


def make_state():
    return create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-1",
        morning_note_id="note-1"
    )


def _tavily_result(articles=None, error=None):
    return TavilyResult(articles=articles or [], error=error)


@pytest.mark.asyncio
async def test_macro_agent_happy_path():
    article = TavilyArticle(
        title="Brazil macro outlook",
        content="Inflation slowed to 3.2%…",
        url="https://example.com/macro",
    )
    result = _tavily_result(articles=[article])

    with patch("app.agents.macro.TavilyService") as MockService:
        MockService.return_value.search = AsyncMock(return_value=result)
        with patch("app.agents.macro.summarize", new=AsyncMock(return_value="Resumo macro de alta confiança.")):
            state = make_state()
            res = await macro_agent_node(state)

    macro = res["macro_context"]
    assert macro is not None
    assert macro["headline"] == "Brazil macro outlook"
    assert macro["summary"] == "Resumo macro de alta confiança."
    assert macro["sources"] == ["https://example.com/macro"]
    assert isinstance(res["data_freshness"]["macro"], datetime)
    assert res["flags"] == []


@pytest.mark.asyncio
async def test_macro_agent_tavily_failure():
    from app.utils.flags import Severity
    error = DataFlag(source="tavily", severity=Severity.WARNING, message="Tavily request error: network down")
    result = _tavily_result(error=error)

    with patch("app.agents.macro.TavilyService") as MockService:
        MockService.return_value.search = AsyncMock(return_value=result)
        state = make_state()
        res = await macro_agent_node(state)

    assert res["macro_context"] is None
    flag = res["flags"][-1]
    assert isinstance(flag, DataFlag)
    assert flag.source == "tavily"
    assert isinstance(res["data_freshness"]["macro"], datetime)


@pytest.mark.asyncio
async def test_macro_agent_tavily_config_error():
    from app.services.tavily import TavilyConfigError
    with patch("app.agents.macro.TavilyService", side_effect=TavilyConfigError("TAVILY_API_KEY missing or empty")):
        state = make_state()
        res = await macro_agent_node(state)

    assert res["macro_context"] is None
    flag = res["flags"][-1]
    assert isinstance(flag, DataFlag)
    assert flag.source == "tavily"
    assert flag.severity.value == "fatal"


@pytest.mark.asyncio
async def test_macro_agent_llm_none():
    article = TavilyArticle(
        title="Brazil macro outlook",
        content="Inflation slowed …",
        url="https://example.com/macro",
    )
    result = _tavily_result(articles=[article])

    with patch("app.agents.macro.TavilyService") as MockService:
        MockService.return_value.search = AsyncMock(return_value=result)
        with patch("app.agents.macro.summarize", new=AsyncMock(return_value=None)):
            state = make_state()
            res = await macro_agent_node(state)

    macro = res["macro_context"]
    assert macro["summary"] == "Inflation slowed …"
    flag = res["flags"][-1]
    assert isinstance(flag, DataFlag)
    assert flag.source == "nvidia_nim"


@pytest.mark.asyncio
async def test_macro_agent_logs_entry(caplog):
    with caplog.at_level(logging.INFO, logger="app.agents.macro"):
        with patch("app.agents.macro.TavilyService") as MockService:
            MockService.return_value.search = AsyncMock(return_value=_tavily_result())
            await macro_agent_node(make_state())
    records = [r for r in caplog.records if r.name == "app.agents.macro"]
    assert len(records) >= 1
    rec = records[0]
    assert rec.pipeline_run_id == "run-1"
    assert rec.morning_note_id == "note-1"
    assert rec.manager_id == 1
