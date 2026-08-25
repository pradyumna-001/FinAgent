import pytest
from unittest.mock import patch
from app.agents.macro import macro_agent_node
from app.graph.state import create_initial_state, Severity


@pytest.mark.asyncio
async def test_macro_agent_no_key():
    with patch("app.agents.macro.settings.TAVILY_API_KEY", ""):
        state = create_initial_state(
            manager_id=1, company_ticker="PETR4",
            pipeline_run_id="run", morning_note_id="note"
        )
        result = await macro_agent_node(state)

    assert result["macro_context"] is None
    assert any(
        f.source == "tavily" and f.severity == Severity.FATAL
        for f in result["flags"]
    )