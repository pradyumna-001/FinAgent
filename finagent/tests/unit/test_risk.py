import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.graph.state import create_initial_state, AgentState, MacroOutput, QuantOutput, CompanyEvent, RiskFlag
from app.utils.data_preprocessing import DataFlag
from app.agents.risk import risk_agent_node

@pytest.fixture
def base_state() -> AgentState:
    """Generates a default initial state loaded with mock upstream data products."""
    state = create_initial_state(
        pipeline_run_id="test-risk-123",
        morning_note_id="test-note-456",
        manager_id=1,
        company_ticker="PETR4"
    )
    
    # Hydrate with mock base agent insights
    state["macro_context"] = MacroOutput(
        gdp_growth=2.1,
        inflation_rate=4.5,
        interest_rate=10.5,
        analysis_summary="Macro headwinds present due to tight monetary constraints."
    )
    state["quant_metrics"] = QuantOutput(
        pe_ratio=5.2,
        ev_ebitda=4.1,
        dividend_yield=9.5,
        momentum_signal="neutral",
        interpretation="Value multi-multipliers look strong but sector risks remain."
    )
    state["company_events"] = [
        CompanyEvent(
            event_name="Earnings Release",
            event_date=datetime.now(timezone.utc),
            significance="high",
            description="Q2 results reporting increased extraction operating costs."
        )
    ]
    return state

@patch("app.agents.risk.PromptManagementService")
@patch("app.agents.risk.OpenAI")
def test_risk_agent_node_success(mock_openai, mock_prompt, base_state):
    """Verifies successful adversarial risk profiling and schema extraction tracks."""
    # Mock prompt loader
    mock_tmpl = MagicMock()
    mock_tmpl.format.return_value = "Formatted Prompt Template Context"
    mock_prompt_instance = MagicMock()
    mock_prompt_instance.load_prompt.return_value = mock_tmpl
    mock_prompt.return_value = mock_prompt_instance

    # Mock OpenAI completion payload
    mock_openai_instance = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = """
    {
        "risks": [
            {
                "risk_type": "Regulatory",
                "severity": "high",
                "description": "Government intervention risk regarding fuel pricing models."
            },
            {
                "risk_type": "Operational",
                "severity": "medium",
                "description": "Rising extraction costs threatening profit margin health."
            }
        ]
    }
    """
    mock_openai_instance.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    mock_openai.return_value = mock_openai_instance

    # Execute target node with mocked environmental configs
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-key"}):
        updated_state = risk_agent_node(base_state)

    # Assertions
    assert len(updated_state["risk_flags"]) == 2
    assert isinstance(updated_state["risk_flags"][0], RiskFlag)
    assert updated_state["risk_flags"][0].risk_type == "Regulatory"
    assert updated_state["risk_flags"][0].severity == "high"
    assert "risk" in updated_state["data_freshness"]
    assert len(updated_state["flags"]) == 0

@patch("app.agents.risk.PromptManagementService")
@patch("app.agents.risk.OpenAI")
def test_risk_agent_node_llm_failure_appends_flag(mock_openai, mock_prompt, base_state):
    """Verifies that an LLM parsing error logs a visible DataFlag warning on state."""
    # Mock templates
    mock_tmpl = MagicMock()
    mock_tmpl.format.return_value = "Formatted Context"
    mock_prompt_instance = MagicMock()
    mock_prompt_instance.load_prompt.return_value = mock_tmpl
    mock_prompt.return_value = mock_prompt_instance

    # Force a network or formatting exception inside OpenAI invocation
    mock_openai_instance = MagicMock()
    mock_openai_instance.chat.completions.create.side_effect = Exception("OpenRouter Connection Timeout (504)")
    mock_openai.return_value = mock_openai_instance

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-key"}):
        updated_state = risk_agent_node(base_state)

    # Assertions
    assert len(updated_state["risk_flags"]) == 0
    assert len(updated_state["flags"]) == 1
    assert updated_state["flags"][0].source == "risk_agent"
    assert updated_state["flags"][0].flag_type == "high"
    assert "OpenRouter generation, parsing, or validation failed" in updated_state["flags"][0].metadata.get("error")
