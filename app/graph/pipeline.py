
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from app.agents.approval_gate import approval_gate_node
from app.agents.company import company_agent_node
from app.agents.consolidate import consolidate_node
from app.agents.editor import editor_agent_node
from app.agents.finalize import finalize_morning_note_node
from app.agents.macro import macro_agent_node
from app.agents.persist import persist_recommendation_node
from app.agents.quant import quant_agent_node
from app.agents.risk import risk_agent_node
from app.agents.send import send_note_node
from app.graph.serialization import get_serializer
from app.graph.state import AgentState, InvalidStateError, create_initial_state


def validated_node(node_fn, name: str):
    async def wrapper(state: AgentState) -> AgentState:
        InvalidStateError().validate(state)
        return await node_fn(state)
    wrapper.__name__ = name
    return wrapper


def fan_out_company(state: AgentState) -> list[Send]:
    """Fan out to company agent for each ticker."""
    return [
        Send("company", {"current_ticker": t, "company_tickers": [t]})
        for t in state["company_tickers"]
    ]


def fan_out_quant(state: AgentState) -> list[Send]:
    """Fan out to quant agent for each ticker."""
    return [
        Send("quant", {"current_ticker": t, "company_tickers": [t]})
        for t in state["company_tickers"]
    ]


def fan_out_risk(state: AgentState) -> list[Send]:
    """Fan out to risk agent for each ticker."""
    return [
        Send("risk", {"current_ticker": t, "company_tickers": [t]})
        for t in state["company_tickers"]
    ]


builder = StateGraph(AgentState)

# Macro runs once (global context)
builder.add_node("macro", validated_node(macro_agent_node, "macro"))

# Per-ticker agents (fan-out targets)
builder.add_node("company", validated_node(company_agent_node, "company"))
builder.add_node("quant", validated_node(quant_agent_node, "quant"))
builder.add_node("risk", validated_node(risk_agent_node, "risk"))

# Consolidate runs once on merged per-ticker state
builder.add_node("consolidate", validated_node(consolidate_node, "consolidate"))

# Editor runs once on full state (per-ticker + portfolio)
builder.add_node("editor", validated_node(editor_agent_node, "editor"))

# Persistence & delivery (unchanged)
builder.add_node("persist", validated_node(persist_recommendation_node, "persist"))
builder.add_node("send", validated_node(send_note_node, "send"))
builder.add_node("approval_gate", validated_node(approval_gate_node, "approval_gate"))
builder.add_node("finalize", validated_node(finalize_morning_note_node, "finalize"))

# Edges
builder.add_edge(START, "macro")

# Fan-out: macro -> company (parallel per ticker)
builder.add_conditional_edges("macro", fan_out_company, ["company"])

# Fan-out: company -> quant (parallel per ticker)
builder.add_conditional_edges("company", fan_out_quant, ["quant"])

# Fan-out: quant -> risk (parallel per ticker)
builder.add_conditional_edges("quant", fan_out_risk, ["risk"])

# risk -> consolidate -> editor -> persist -> send -> approval_gate -> finalize
builder.add_edge("risk", "consolidate")
builder.add_edge("consolidate", "editor")
builder.add_edge("editor", "persist")
builder.add_edge("persist", "send")
builder.add_edge("send", "approval_gate")
builder.add_edge("approval_gate", "finalize")
builder.add_edge("finalize", END)


def compile_graph(checkpointer) -> CompiledStateGraph:
    return builder.compile(checkpointer=checkpointer)


# Create dev_graph with custom serializer for DataFlag and Severity
_dev_saver = InMemorySaver()
_dev_saver.serde = get_serializer()
dev_graph = builder.compile(checkpointer=_dev_saver)

__all__ = ["compile_graph", "dev_graph", "create_initial_state"]
