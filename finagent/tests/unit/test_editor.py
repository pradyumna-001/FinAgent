import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import pytest

from app.graph.state import create_initial_state, MacroOutput, CompanyEvent, QuantOutput, RiskFlag
from app.utils.data_preprocessing import DataFlag
from app.agents.editor import editor_agent_node

@pytest.fixture
def base_state():
    """Initializes a standard state filled with successful upstream data context"""
    state = create_initial_state(
        pipeline_run_id="test-run-editor",
        morning_note_id="note-editor-123",
        manager_id=42,
        company_ticker="VALE3"
    )
    # Populate successful sample data
    state["macro_context"] = MacroOutput(
        gdp_growth=2.5,
        inflation_rate=4.1,
        interest_rate=10.5,
        analysis_summary="Stable macroeconomic baseline environment."
    )
    state["company_events"] = [
        CompanyEvent(
            event_name="Earnings Release",
            event_date=datetime.now(timezone.utc),
            significance="high",
            description="Q2 operational review."
        )
    ]
    state["quant_metrics"] = QuantOutput(
        pe_ratio=6.2,
        ev_ebitda=4.5,
        dividend_yield=8.2,
        momentum_signal="neutral",
        interpretation="Value multi-year lows."
    )
    state["risk_flags"] = [
        RiskFlag(risk_type="Commodity", severity="medium", description="Iron ore volatility exposure.")
    ]
    return state


@patch("app.agents.editor.OpenAI")
@patch("app.agents.editor.PromptManagementService")
@patch.dict("os.environ", {"OPENROUTER_API_KEY": "fake-key"})
def test_editor_agent_node_success(mock_prompt_service, mock_openai, base_state):
    """Verifies successful compilation when all upstream analytical components are clear"""
    # Mock prompt service
    mock_tmpl = MagicMock()
    mock_tmpl.format.return_value = "Formatted template string"
    mock_prompt_instance = MagicMock()
    mock_prompt_instance.load_prompt.return_value = mock_tmpl
    mock_prompt_service.return_value = mock_prompt_instance

    # Mock OpenAI client response payload
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps({
                    "morning_note": "### Contexto Macro\nTexto aqui.\n### Eventos Corporativos\nTexto.\n### Métricas Quantitativas\nDados.\n### Fatores de Risco\nRiscos.\n### Recomendação de Investimento\nComprar.",
                    "action": "BUY",
                    "target_weight": 5.5,
                    "horizon_months": 12,
                    "thesis_summary": "Strong core margins and defensive balance sheet."
                })
            )
        )
    ]
    mock_openai.return_value.chat.completions.create.return_value = mock_response

    # Run node
    final_state = editor_agent_node(base_state)

    # Asserts
    assert final_state["morning_note"] is not None
    assert "Contexto Macro" in final_state["morning_note"]
    assert final_state["recommendation"] is not None
    assert final_state["recommendation"].action == "BUY"
    assert final_state["recommendation"].target_weight == 5.5
    
    # Check that baseline confidence scores default to high (0.9) when no flags exist
    assert final_state["confidence_scores"]["macro"] == 0.9
    assert final_state["confidence_scores"]["risk"] == 0.9
    assert "editor" in final_state["data_freshness"]


@patch("app.agents.editor.OpenAI")
@patch("app.agents.editor.PromptManagementService")
@patch.dict("os.environ", {"OPENROUTER_API_KEY": "fake-key"})
def test_editor_agent_fail_visible_on_data_flags(mock_prompt_service, mock_openai, base_state):
    """Verifies that an upstream DataFlag penalizes section confidence and sets up fail visibility"""
    # Inject an intentional data flag caused by a macro agent failure
    base_state["flags"].append(
        DataFlag(
            source="macro_agent",
            flag_type="high",
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={"error": "Tavily timeout encountered"}
        )
    )

    mock_tmpl = MagicMock()
    mock_tmpl.format.return_value = "Formatted prompt string"
    mock_prompt_instance = MagicMock()
    mock_prompt_instance.load_prompt.return_value = mock_tmpl
    mock_prompt_service.return_value = mock_prompt_instance

    # Mock response containing the requested visible warning banner inside the affected section
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps({
                    "morning_note": "### Contexto Macro\n⚠️ **[AVISO DE LACUNA DE DADOS: ESTA SEÇÃO APRESENTA INFORMAÇÕES INCOMPLETAS...]**",
                    "action": "HOLD",
                    "target_weight": 2.0,
                    "horizon_months": 12,
                    "thesis_summary": "Incomplete pipeline overview."
                })
            )
        )
    ]
    mock_openai.return_value.chat.completions.create.return_value = mock_response

    # Run node
    final_state = editor_agent_node(base_state)

    # Asserts
    assert final_state["confidence_scores"]["macro"] < 0.5  # Penalized
    assert final_state["confidence_scores"]["company"] == 0.9  # Untouched
    assert "⚠️" in final_state["morning_note"] and "AVISO DE LACUNA DE DADOS" in final_state["morning_note"]

@patch.dict("os.environ", {"OPENROUTER_API_KEY": ""})
def test_editor_agent_missing_api_key_graceful_fallback(base_state):
    """Ensures missing infrastructure parameters append a terminal data flag"""
    final_state = editor_agent_node(base_state)
    
    assert final_state["morning_note"] is None
    assert final_state["recommendation"] is None
    assert any(f.source == "editor_agent" for f in final_state["flags"])
