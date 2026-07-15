import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.agents.macro import macro_agent_node
from app.graph.state import AgentState, MacroOutput

@pytest.fixture
def base_state() -> AgentState:
    """Fixture to provide a clean, initial AgentState setup"""
    return {
        "pipeline_run_id": "test-run-123",
        "morning_note_id": "test-note-456",
        "macro_context": None,
        "flags": [],
        "data_freshness": {
            "macro": None,
            "tickers": {}
        }
    }

@patch("app.agents.macro.TavilyClient")
@patch("app.agents.macro.genai.Client")
@patch("os.getenv")
def test_macro_agent_node_happy_path(
    mock_getenv, mock_genai_client_class,
    mock_tavily_class, base_state
):
    """Tests the successful (happy) path of the MacroAgent"""
    mock_getenv.side_effect = lambda key, default=None: {
        "GEMINI_API_KEY": "fake_gemini_key",
        "TAVILY_API_KEY": "fake_tavily_key"
    }.get(key, default)

    mock_tavily_instance = MagicMock()
    mock_tavily_class.return_value = mock_tavily_instance
    mock_tavily_instance.get_search_context.return_value = "Mocked macroeconomic news text"

    mock_genai_client = MagicMock()
    mock_genai_client_class.return_value = mock_genai_client

    mock_response = MagicMock()
    mock_response.text = '{"gdp_growth": 2.5, "inflation_rate": 4.1, "interest_rate": 10.5, "analysis_summary": "Brazilian economy looks stable."}'
    mock_genai_client.models.generate_content.return_value = mock_response

    updated_state = macro_agent_node(base_state)

    assert updated_state["macro_context"] is not None
    assert isinstance(updated_state["macro_context"], MacroOutput)
    assert updated_state["macro_context"].gdp_growth == 2.5
    assert updated_state["macro_context"].inflation_rate == 4.1
    assert updated_state["macro_context"].interest_rate == 10.5
    assert updated_state["macro_context"].analysis_summary == "Brazilian economy looks stable."

    assert updated_state["data_freshness"]["macro"] is not None
    assert isinstance(updated_state["data_freshness"]["macro"], datetime)

    assert len(updated_state["flags"]) == 0

@patch("app.agents.macro.TavilyClient")
@patch("os.getenv")
def test_macro_agent_node_tavily_failure_fallback(
    mock_getenv, mock_tavily_class, base_state
):
    """Tests graceful degradation when Tavily fails"""
    mock_getenv.side_effect = lambda key, default=None: {
        "GEMINI_API_KEY": "fake_gemini_key",
        "TAVILY_API_KEY": "fake_tavily_key"
    }.get(key, default)

    mock_tavily_instance = MagicMock()
    mock_tavily_class.return_value = mock_tavily_instance
    mock_tavily_instance.get_search_context.side_effect = Exception("Tavily Service Unavailable")

    updated_state = macro_agent_node(base_state)
    
    assert updated_state["macro_context"] is None
    assert len(updated_state["flags"]) == 1

    failure_flag = updated_state["flags"][0]
    assert failure_flag.source == "macro_agent"
    assert failure_flag.flag_type == "high"
    assert isinstance(failure_flag.timestamp, str)
