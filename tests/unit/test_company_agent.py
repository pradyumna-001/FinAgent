import pytest

from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.company import company_agent_node
from app.graph.state import create_initial_state, Severity


@pytest.mark.asyncio
async def test_company_agent_no_key():
    with patch("app.agents.company.settings.TAVILY_API_KEY", ""):
        state = create_initial_state(
            manager_id=1, company_ticker="PETR4",
            pipeline_run_id="run", morning_note_id="note",
        )
        result = await company_agent_node(state)

    assert result["company_events"] == []
    assert any(
        f.source == "tavily" and f.severity == Severity.FATAL
        for f in result["flags"]
    )
    from datetime import datetime
    assert isinstance(result["data_freshness"]["company"], datetime)


@pytest.mark.asyncio
async def test_company_agent_llm_none():
    tavily_json = {
        "results": [
            {
                "title": "PETR4 earnings Q3",
                "content": "Petrobras reported record earnings...",
                "url": "https://infomoney.com.br/petr4",
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

    with patch("app.agents.company.settings.TAVILY_API_KEY", "dummy"):
        with patch("app.agents.company.httpx.AsyncClient", return_value=mock_client):
            with patch("app.agents.company.summarize", side_effect=summarize_returns_none):
                state = create_initial_state(
                    manager_id=1, company_ticker="PETR4",
                    pipeline_run_id="run", morning_note_id="note",
                )
                result = await company_agent_node(state)

    events = result["company_events"]
    assert len(events) == 1
    assert events[0]["summary"] == "Petrobras reported record earnings..."
    flag = result["flags"][-1]
    assert flag.source == "nvidia_nim"


@pytest.mark.asyncio
async def test_company_agent_happy_path():
    tavily_json = {
        "results": [
            {
                "title": "PETR4 earnings Q3",
                "content": "Petrobras reported record earnings...",
                "url": "https://infomoney.com.br/petr4",
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
        return "Resumo de earnings da Petrobras."

    with patch("app.agents.company.settings.TAVILY_API_KEY", "dummy"):
        with patch("app.agents.company.httpx.AsyncClient", return_value=mock_client):
            with patch("app.agents.company.summarize", side_effect=fake_summarize):
                state = create_initial_state(
                    manager_id=1, company_ticker="PETR4",
                    pipeline_run_id="run", morning_note_id="note",
                )
                result = await company_agent_node(state)

    events = result["company_events"]
    assert len(events) == 1
    assert events[0]["title"] == "PETR4 earnings Q3"
    assert events[0]["summary"] == "Resumo de earnings da Petrobras."
    assert events[0]["source"] == "https://infomoney.com.br/petr4"
    from datetime import datetime
    assert isinstance(result["data_freshness"]["company"], datetime)
    assert result["flags"] == []


