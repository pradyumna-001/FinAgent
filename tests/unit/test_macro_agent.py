import logging
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

from app.agents.macro import macro_agent_node
from app.graph.state import create_initial_state, DataFlag, Severity


def make_state():
    return create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-1",
        morning_note_id="note-1",
    )


@pytest.mark.asyncio
async def test_macro_agent_happy_path():
    tavily_json = {
        "results": [
            {
                "title": "Brazil macro outlook",
                "content": "Inflation slowed to 3.2%…",
                "url": "https://example.com/macro",
            }
        ]
    }

    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = tavily_json
    mock_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client

    async def fake_summarize(system: str, user: str):
        return "Resumo macro de alta confiança."

    with patch("app.core.config.settings.TAVILY_API_KEY", "dummy"):
        with patch("app.agents.macro.httpx.AsyncClient", return_value=mock_client):
            with patch("app.agents.macro.summarize", side_effect=fake_summarize):
                state = make_state()
                result = await macro_agent_node(state)

    macro = result["macro_context"]
    assert macro is not None
    assert macro["headline"] == "Brazil macro outlook"
    assert macro["summary"] == "Resumo macro de alta confiança."
    assert macro["sources"] == ["https://example.com/macro"]
    # freshness should be a datetime
    assert isinstance(result["data_freshness"]["macro"], datetime)
    assert result["flags"] == []


@pytest.mark.asyncio
async def test_macro_agent_tavily_failure():
    mock_client = AsyncMock()
    mock_client.post.side_effect = Exception("network down")
    mock_client.__aenter__.return_value = mock_client

    with patch("app.core.config.settings.TAVILY_API_KEY", "dummy"):
        with patch("app.agents.macro.httpx.AsyncClient", return_value=mock_client):
            state = make_state()
            result = await macro_agent_node(state)

    assert result["macro_context"] is None
    flag = result["flags"][-1]
    assert isinstance(flag, DataFlag)
    assert flag.source == "tavily"
    assert isinstance(result["data_freshness"]["macro"], datetime)


@pytest.mark.asyncio
async def test_macro_agent_llm_none():
    tavily_json = {
        "results": [
            {
                "title": "Brazil macro outlook",
                "content": "Inflation slowed …",
                "url": "https://example.com/macro",
            }
        ]
    }

    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = tavily_json
    mock_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client

    async def summarize_returns_none(system, user):
        return None

    with patch("app.core.config.settings.TAVILY_API_KEY", "dummy"):
        with patch("app.agents.macro.httpx.AsyncClient", return_value=mock_client):
            with patch("app.agents.macro.summarize", side_effect=summarize_returns_none):
                state = make_state()
                result = await macro_agent_node(state)

    macro = result["macro_context"]
    assert macro["summary"] == "Inflation slowed …"
    flag = result["flags"][-1]
    assert isinstance(flag, DataFlag)
    assert flag.source == "tavily"


@pytest.mark.asyncio
async def test_macro_agent_logs_entry(caplog):
    """Verify the logger emits an info record with correlation IDs at entry."""
    state = make_state()
    with caplog.at_level(logging.INFO, logger="app.agents.macro"):
        result = await macro_agent_node(state)
    records = [r for r in caplog.records if r.name == "app.agents.macro"]
    assert len(records) >= 1
    rec = records[0]
    assert rec.pipeline_run_id == state["pipeline_run_id"]
    assert rec.morning_note_id == state["morning_note_id"]
    assert rec.manager_id == state["manager_id"]