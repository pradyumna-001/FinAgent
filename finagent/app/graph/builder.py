import logging
from functools import wraps
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from app.graph.state import AgentState, validate_state
from app.agents.macro import macro_agent_node
from app.agents.company import company_agent_node
from app.agents.quant import quant_agent_node
from app.agents.risk import risk_agent_node
from app.agents.editor import editor_agent_node

logger = logging.getLogger("finagent.graph.builder")

def _wrap_with_validation(node_func):
    """
    Decorator wrapper that enforces data integrity checks at node boundaries
    while fully preserving functional metadata (__name__, __doc__) for LangSmith.
    """
    @wraps(node_func)
    def validated_node(state: AgentState) -> AgentState:
        # Enforce pre-execution state validation
        validate_state(state)
        return node_func(state)
    return validated_node

def create_financial_agent_graph() -> CompiledStateGraph:
    """
    Factory function that assembles and compiles the multi-agent execution pipeline.
    
    Topology Graph Architecture (ADR-006 / Parallel Fan-Out/Fan-In):
        START ──> macro_agent ──┬──> company_agent ──┬──> risk_agent ──> editor_agent ──> END
                                └──> quant_agent ───┘
    """
    logger.info("Assembling financial multi-agent graph network.")
    
    # 1. Initialize StateGraph using our custom TypedDict schema
    workflow = StateGraph(AgentState)
    
    # 2. Register analytical nodes with metadata-preserving validation wrappers
    workflow.add_node("macro_agent", _wrap_with_validation(macro_agent_node))
    workflow.add_node("company_agent", _wrap_with_validation(company_agent_node))
    workflow.add_node("quant_agent", _wrap_with_validation(quant_agent_node))
    workflow.add_node("risk_agent", _wrap_with_validation(risk_agent_node))
    workflow.add_node("editor_agent", _wrap_with_validation(editor_agent_node))
    
    # 3. Wire Graph Edge Networks
    workflow.add_edge(START, "macro_agent")
    
    # Fan-Out: Branch into concurrent execution streams for speed optimization
    workflow.add_edge("macro_agent", "company_agent")
    workflow.add_edge("macro_agent", "quant_agent")
    
    # Fan-In: Wait for both streams to conclude before executing adversarial audit
    workflow.add_edge("company_agent", "risk_agent")
    workflow.add_edge("quant_agent", "risk_agent")
    
    # Final editorial aggregation and pipeline exit
    workflow.add_edge("risk_agent", "editor_agent")
    workflow.add_edge("editor_agent", END)
    
    # 4. Compile the Directed Acyclic Graph (DAG)
    compiled_graph = workflow.compile()
    
    logger.info("Multi-agent graph compiled successfully as a CompiledStateGraph instance.")
    return compiled_graph
