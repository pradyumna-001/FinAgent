import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.graph.state import AgentState, CompanyEvent
from app.utils.data_preprocessing import DataFlag
from app.agents.company import company_agent_node

@pytest.fixture
def base_state() -> AgentState:
    return {
        "pipeline_run_id": "test-run-123",
        "morning_note_id": "test-note-456",
        "company_ticker": "PETR4",
        "flags": [],
        "data_freshness": {},
        "company_events": []
    }

@patch("app.agents.company.PromptManagementService")
@patch("app.agents.company.TavilyClient")
@patch("app.agents.company.OpenAI")
def test_company_agent_node_success(
    mock_openai_class, mock_tavily_class,
    mock_prompt_service_class, base_state
):
    # Fix 1: Make format return a plain string regardless of how it is called
    # (handles the single dictionary vs kwargs problem gracefully)
    mock_system_prompt = MagicMock()
    mock_system_prompt.format.return_value = "Mocked System Prompt Content"

    mock_user_prompt = MagicMock()
    mock_user_prompt.format.return_value = "Mocked User Prompt Content"

    mock_prompt_instance = MagicMock()
    mock_prompt_instance.load_prompt.side_effect = lambda name: (
        mock_system_prompt if "system" in name else mock_user_prompt
    )
    mock_prompt_service_class.return_value = mock_prompt_instance

    mock_tavily_instance = MagicMock()
    mock_tavily_instance.get_search_context.return_value = "Fato Relevante: Dividendos distribuidos pela Petrobras."
    mock_tavily_class.return_value = mock_tavily_instance

    mock_openai_instance = MagicMock()
    
    # Fix 2: Explicitly provide 'significance' inside the JSON to align with the final asset check
    mock_json_response = """{
        "events": [{
            "event_name": "Dividendos PETR4",
            "description": "Petrobras aprova distribuição de dividendos bilionarios.",
            "event_date": "2026-07-15",
            "impact": "positive",
            "significance": "medium"
        }]
    }"""

    mock_choice = MagicMock()
    mock_choice.message.content = mock_json_response
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_openai_instance.chat.completions.create.return_value = mock_response
    mock_openai_class.return_value = mock_openai_instance

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "fake_key", "TAVILY_API_KEY": "fake_key"}):
        updated_state = company_agent_node(base_state)
        
    assert isinstance(updated_state["company_events"], list)
    assert len(updated_state["company_events"]) == 1

    first_event = updated_state["company_events"][0]
    assert isinstance(first_event, CompanyEvent)
    assert first_event.event_name == "Dividendos PETR4"
    assert first_event.significance == "medium"

    assert len(updated_state["flags"]) == 0
    assert "company" in updated_state["data_freshness"]

@patch("app.agents.company.PromptManagementService")
@patch("app.agents.company.TavilyClient")
@patch("app.agents.company.OpenAI")
def test_company_agent_node_api_failure(
    mock_openai_class, mock_tavily_class,
    mock_prompt_service_class, base_state
):
    mock_prompt_instance = MagicMock()
    mock_prompt_service_class.return_value = mock_prompt_instance
    
    mock_tavily_instance = MagicMock()
    mock_tavily_instance.get_search_context.side_effect = Exception("Tavily API Timeout Error")
    mock_tavily_class.return_value = mock_tavily_instance

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "fake_key", "TAVILY_API_KEY": "fake_key"}):
        updated_state = company_agent_node(base_state)

    assert updated_state["company_events"] == []
    assert len(updated_state["flags"]) == 1

    assert updated_state["flags"][0].source == "company_agent"
    assert updated_state["flags"][0].flag_type == "high"