import pytest
from unittest.mock import patch, MagicMock
from langgraph.graph.state import CompiledStateGraph

from app.graph.builder import create_financial_agent_graph, _wrap_with_validation
from app.graph.state import create_initial_state, AgentState

# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def graph() -> CompiledStateGraph:
    return create_financial_agent_graph()

@pytest.fixture
def valid_state() -> AgentState:
    return create_initial_state(
        pipeline_run_id="test-run-builder",
        morning_note_id="test-note-builder",
        manager_id=1,
        company_ticker="PETR4"
    )

@pytest.fixture
def invalid_state() -> AgentState:
    state = create_initial_state(
        pipeline_run_id="test-run-builder",
        morning_note_id="test-note-builder",
        manager_id=1,
        company_ticker="PETR4"
    )
    state["manager_id"] = None  # Intentionally breaking structure rules
    return state

# ─── Graph Structure Tests ───────────────────────────────────────────────────

def test_graph_compiles_successfully(graph):
    """Factory must return a compiled LangGraph instance."""
    assert isinstance(graph, CompiledStateGraph)

def test_graph_has_all_nodes(graph):
    """All five agent nodes must be registered in the compiled graph."""
    node_names = set(graph.nodes.keys())
    expected = {"macro_agent", "company_agent", "quant_agent", "risk_agent", "editor_agent"}
    assert expected.issubset(node_names)

def test_graph_is_independent_per_call():
    """Each call to the factory must return a distinct compiled instance."""
    g1 = create_financial_agent_graph()
    g2 = create_financial_agent_graph()
    assert g1 is not g2

# ─── Validation Wrapper Tests ────────────────────────────────────────────────

def test_wrap_preserves_function_name():
    """_wrap_with_validation must preserve __name__ for LangSmith trace readability."""
    def my_agent_node(state):
        return state

    wrapped = _wrap_with_validation(my_agent_node)
    assert wrapped.__name__ == "my_agent_node"

def test_wrap_calls_validate_state_before_node(valid_state):
    """Wrapped node must call validate_state before executing the inner function."""
    execution_order = []

    with patch("app.graph.builder.validate_state", side_effect=lambda s: execution_order.append("validate")):
        def mock_node(state):
            execution_order.append("node")
            return state

        wrapped = _wrap_with_validation(mock_node)
        wrapped(valid_state)

    assert execution_order == ["validate", "node"]

def test_wrap_blocks_invalid_state(invalid_state):
    """Wrapped node must raise a ValueError when the input state format is compromised."""
    called = []

    def should_not_be_called(state):
        called.append(True)
        return state

    wrapped = _wrap_with_validation(should_not_be_called)

    with pytest.raises(ValueError, match="State Invariant Violation"):
        wrapped(invalid_state)

    assert called == [], "Inner node must not execute when state validation fails."

def test_wrap_passes_state_through(valid_state):
    """Wrapped node must return whatever updates the inner function generates."""
    def identity_node(state):
        state["company_ticker"] = "VALE3"
        return state

    wrapped = _wrap_with_validation(identity_node)
    result = wrapped(valid_state)

    assert result["company_ticker"] == "VALE3"

# ─── Topology Tests ──────────────────────────────────────────────────────────

def test_parallel_execution_macro_fans_out(valid_state):
    """
    After macro_agent, both company_agent and quant_agent must execute.
    Verifies fan-out topology — ADR-006.
    """
    execution_log = []

    def make_mock_node(name):
        def node(state):
            execution_log.append(name)
            return {}  # CRITICAL FIX: Return only updates (none), not the entire state dict
        node.__name__ = name
        return node

    with patch("app.graph.builder.macro_agent_node",   make_mock_node("macro")), \
         patch("app.graph.builder.company_agent_node", make_mock_node("company")), \
         patch("app.graph.builder.quant_agent_node",   make_mock_node("quant")), \
         patch("app.graph.builder.risk_agent_node",    make_mock_node("risk")), \
         patch("app.graph.builder.editor_agent_node",  make_mock_node("editor")):

        graph = create_financial_agent_graph()
        graph.invoke(valid_state)

    assert "macro"   in execution_log
    assert "company" in execution_log
    assert "quant"   in execution_log
    assert "risk"    in execution_log
    assert "editor"  in execution_log

def test_risk_runs_after_parallel_agents(valid_state):
    """
    risk_agent must execute after both company_agent and quant_agent have finished.
    Verifies fan-in topology boundaries.
    """
    execution_log = []

    def make_mock_node(name):
        def node(state):
            execution_log.append(name)
            return {}  # CRITICAL FIX: Return only updates (none), not the entire state dict
        node.__name__ = name
        return node

    with patch("app.graph.builder.macro_agent_node",   make_mock_node("macro")), \
         patch("app.graph.builder.company_agent_node", make_mock_node("company")), \
         patch("app.graph.builder.quant_agent_node",   make_mock_node("quant")), \
         patch("app.graph.builder.risk_agent_node",    make_mock_node("risk")), \
         patch("app.graph.builder.editor_agent_node",  make_mock_node("editor")):

        graph = create_financial_agent_graph()
        graph.invoke(valid_state)

    risk_idx    = execution_log.index("risk")
    company_idx = execution_log.index("company")
    quant_idx   = execution_log.index("quant")

    assert risk_idx > company_idx, "Risk node execution must wait for company_agent completion."
    assert risk_idx > quant_idx,   "Risk node execution must wait for quant_agent completion."

def test_editor_runs_last(valid_state):
    """editor_agent must be the terminal node executed before graph finalization."""
    execution_log = []

    def make_mock_node(name):
        def node(state):
            execution_log.append(name)
            return {}  # CRITICAL FIX: Return only updates (none), not the entire state dict
        node.__name__ = name
        return node

    with patch("app.graph.builder.macro_agent_node",   make_mock_node("macro")), \
         patch("app.graph.builder.company_agent_node", make_mock_node("company")), \
         patch("app.graph.builder.quant_agent_node",   make_mock_node("quant")), \
         patch("app.graph.builder.risk_agent_node",    make_mock_node("risk")), \
         patch("app.graph.builder.editor_agent_node",  make_mock_node("editor")):

        graph = create_financial_agent_graph()
        graph.invoke(valid_state)

    assert execution_log[-1] == "editor", "The final execution node must be the editor_agent."