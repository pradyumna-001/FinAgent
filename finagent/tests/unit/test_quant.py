import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.graph.state import AgentState, QuantOutput
from app.agents.quant import quant_agent_node

@pytest.fixture
def base_state() -> AgentState:
    return {
        "pipeline_run_id": "test-quant-123",
        "morning_note_id": "test-note-456",
        "company_ticker": "PETR4",
        "flags": [],
        "data_freshness": {"company": datetime.now(timezone.utc)},
        "quant_metrics": None
    }

@patch("app.agents.quant.yf.Ticker")
@patch("app.agents.quant.PromptManagementService")
@patch("app.agents.quant.OpenAI")
def test_quant_agent_node_fresh_success(
    mock_openai, mock_prompt_service,
    mock_yf_ticker, base_state
):
    mock_stock = MagicMock()
    mock_stock.info = {
        "currentPrice": 40.00,
        "trailingEps": 4.0,
        "enterpriseValue": 200000,
        "ebitda": 50000,
        "bookValue": 20.0,
        "dividendYield": 0.05
    }
    mock_yf_ticker.return_value = mock_stock

    mock_tmpl = MagicMock()
    mock_tmpl.raw_template = "Mocked template data string"
    mock_prompt_instance = MagicMock()
    mock_prompt_instance.load_prompt.return_value = mock_tmpl
    mock_prompt_service.return_value = mock_prompt_instance

    mock_openai_instance = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Comentário qualitativo simulado com sinal de alta."
    mock_openai_instance.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_openai.return_value = mock_openai_instance

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "fake_key"}):
        updated_state = quant_agent_node(base_state)

    assert updated_state["quant_metrics"] is not None
    metrics = updated_state["quant_metrics"]

    assert metrics.pe_ratio == 10.0
    assert metrics.ev_ebitda == 4.0
    assert metrics.dividend_yield == 5.0
    assert metrics.momentum_signal == "bullish"
    assert len(updated_state["flags"]) == 0

def test_quant_agent_node_stale_data_guard(base_state):
    base_state["data_freshness"]["company"] = datetime.now(timezone.utc) - timedelta(hours=48)

    updated_state = quant_agent_node(base_state)

    assert updated_state.get("quant_metrics") is None
    assert len(updated_state["flags"]) == 1
    assert updated_state["flags"][0].source == "b3_api"
    assert updated_state["flags"][0].metadata.get("error") == "data_outdated"
