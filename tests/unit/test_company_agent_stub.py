import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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


async def _summarize_returns_none(system, user):
    return None


@pytest.mark.asyncio
async def test_company_agent_all_null_fields():
    """Tavily returns results[0] with null title/content → FATAL DataFlag, no raise."""
    tavily_json = {
        "results": [{"title": None, "content": None, "url": None}]
    }

    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = tavily_json
    mock_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client

    with patch("app.agents.company.settings.TAVILY_API_KEY", "dummy"):
        with patch("app.agents.company.httpx.AsyncClient", return_value=mock_client):
            with patch("app.agents.company.summarize", side_effect=_summarize_returns_none):
                state = create_initial_state(
                    manager_id=1, company_ticker="PETR4",
                    pipeline_run_id="run-null", morning_note_id="note-null",
                )
                result = await company_agent_node(state)

    assert result["company_events"] == []
    assert len(result["flags"]) == 1
    flag = result["flags"][0]
    assert flag.source == "tavily"
    assert flag.severity == Severity.FATAL
    assert "PETR4" in flag.message
    assert "parse-block failed" in flag.message