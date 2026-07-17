import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.graph.state import create_initial_state, AgentState
from app.agents.quant import quant_agent_node
from app.agents.macro import macro_agent_node
from app.agents.company import company_agent_node

@pytest.fixture
def clean_pipeline_state() -> AgentState:
    return create_initial_state(
        pipeline_run_id="integration-test-run-999",
        morning_note_id="integration-test-note-999",
        manager_id=1,
        company_ticker="PETR4"
    )

@patch("app.agents.macro.TavilyClient")
@patch("app.agents.macro.OpenAI")
def test_macro_agent_handles_tavily_500_gracefully(mock_openai, mock_tavily, clean_pipeline_state):
    mock_tavily.return_value.search.side_effect = Exception("Tavily Search Error: HTTP 500")

    mock_openai_instance = MagicMock()
    mock_openai.return_value = mock_openai_instance

    final_state = macro_agent_node(clean_pipeline_state)

    assert len(final_state["flags"]) == 1
    assert final_state["flags"][0].source == "macro_agent" or final_state["flags"][0].source == "tavily_api"
    assert "macro" in final_state["data_freshness"] or len(final_state["flags"]) > 0

@patch("app.agents.company.TavilyClient")
@patch("app.agents.company.OpenAI")
def test_company_agent_handles_tavily_500_gracefully(mock_openai, mock_tavily, clean_pipeline_state):
    mock_tavily.return_value.search.side_effect = Exception("Tavily Search Error: HTTP 500")

    mock_openai_instance = MagicMock()
    mock_openai.return_value = mock_openai_instance

    final_state = company_agent_node(clean_pipeline_state)

    assert len(final_state["flags"]) == 1
    assert final_state["flags"][0].flag_type == "high"

@patch("app.agents.quant.yf.Ticker")
@patch("app.agents.quant.PromptManagementService")
@patch("app.agents.quant.OpenAI")
def test_quant_agent_stale_data_blocks_execution(mock_openai, mock_prompt, mock_yf, clean_pipeline_state):
    clean_pipeline_state["data_freshness"]["company"] = datetime.now(timezone.utc) - timedelta(hours=48)

    mock_stock = MagicMock()
    mock_yf.return_value = mock_stock

    final_state = quant_agent_node(clean_pipeline_state)

    assert final_state.get("quant_metrics") is None
    assert len(final_state["flags"]) == 1
    assert final_state["flags"][0].source == "b3_api"
    assert final_state["flags"][0].metadata.get("error") == "data_outdated"

@patch("app.agents.quant.yf.Ticker")
@patch("app.agents.quant.PromptManagementService")
@patch("app.agents.quant.OpenAI")
def test_agent_pipeline_tracks_sequential_freshness(mock_openai, mock_prompt, mock_yf, clean_pipeline_state):
    clean_pipeline_state["data_freshness"]["company"] = datetime.now(timezone.utc)

    mock_stock = MagicMock()
    mock_stock.info = {
        "currentPrice": 40.00,
        "trailingEps": 4.0,
        "enterpriseValue": 200000,
        "ebitda": 50000,
        "dividendYield": 0.05
    }
    mock_yf.return_value = mock_stock

    mock_tmpl = MagicMock()
    mock_tmpl.raw_template = "System Instruction Context"
    mock_prompt_instance = MagicMock()
    mock_prompt_instance.load_prompt.return_value = mock_tmpl
    mock_prompt_value = mock_prompt_instance

    mock_openai_instance = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "bullish narrative interpretation details"
    mock_openai_instance.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_openai.return_value = mock_openai_instance

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test_key"}):
        final_state = quant_agent_node(clean_pipeline_state)

    assert "quant" in final_state["data_freshness"]
    assert isinstance(final_state["data_freshness"]["quant"], datetime)
