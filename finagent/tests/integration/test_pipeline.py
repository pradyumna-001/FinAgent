import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from langgraph.graph.state import CompiledStateGraph

from app.graph.state import create_initial_state, Recommendation
from app.graph.pipeline import run_financial_pipeline

@pytest.fixture
def mock_db_and_graph():
    """Mocks the database connection pool and structural agent node logic."""
    with patch("app.graph.pipeline.ConnectionPool") as mock_pool, \
         patch("app.graph.pipeline.PostgresSaver") as mock_saver, \
         patch("app.graph.pipeline.macro_agent_node") as mock_macro, \
         patch("app.graph.pipeline.company_agent_node") as mock_company, \
         patch("app.graph.pipeline.quant_agent_node") as mock_quant, \
         patch("app.graph.pipeline.risk_agent_node") as mock_risk, \
         patch("app.graph.pipeline.editor_agent_node") as mock_editor:
        
        # Mock agent return values (sparse dicts to prevent concurrent write collisions)
        mock_macro.return_value = {"macro_context": MagicMock()}
        mock_company.return_value = {"company_events": [MagicMock()]}
        mock_quant.return_value = {"quant_metrics": MagicMock()}
        mock_risk.return_value = {"risk_flags": []}
        
        def editor_effect(state):
            state["morning_note"] = "### Executive Summary\nStrong fundamentals verified."
            state["recommendation"] = Recommendation(
                action="BUY",
                target_weight=15.0,
                horizon_months=12,
                thesis_summary="Test thesis pass."
            )
            return state
        mock_editor.side_effect = editor_effect
        
        yield {
            "pool": mock_pool,
            "saver": mock_saver,
            "editor": mock_editor
        }

def test_pipeline_attaches_checkpointing_and_metadata_tags(mock_db_and_graph):
    """
    TDD Test: Verifies that the production runner configures the Postgres checkpointer 
    and passes the structural LangSmith tracking metadata required by Issue #14.
    """
    initial_state = create_initial_state(
        pipeline_run_id="run-tdd-123",
        morning_note_id="note-tdd-456",
        manager_id=42,
        company_ticker="PETR4"
    )
    initial_state["data_freshness"]["company"] = datetime.now(timezone.utc).isoformat()
    
    # We spy on CompiledStateGraph.invoke to inspect what configuration arguments are injected
    with patch.object(CompiledStateGraph, "invoke", autospec=True) as spy_invoke:
        spy_invoke.return_value = {
            **initial_state,
            "morning_note": "Mocked Note",
            "recommendation": Recommendation(action="BUY", target_weight=10.0, thesis_summary="...")
        }
        
        # Execute the wrapper under test
        run_financial_pipeline(initial_state)
        
        # 1. Verify checkpointer initialization was commanded
        mock_db_and_graph["saver"].return_value.setup.assert_called_once()
        
        # 2. Extract configuration payload delivered to the LangGraph execution runtime
        assert spy_invoke.call_count == 1
        called_args, called_kwargs = spy_invoke.call_args
        
        config = called_kwargs.get("config", {})
        metadata = config.get("metadata", {})
        tags = config.get("tags", [])
        
        # 3. Enforce precise LangSmith tracking specifications (Issue #14)
        assert metadata["manager_id"] == 42
        assert metadata["company"] == "PETR4"
        assert metadata["pipeline_run_id"] == "run-tdd-123"
        assert metadata["morning_note_id"] == "note-tdd-456"
        assert "date" in metadata
        
        assert "manager:42" in tags
        assert "ticker:PETR4" in tags
        assert "thread_id" in config.get("configurable", {})

