from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import InMemorySaver

from app.db.session import engine
from app.graph.state import AgentState, InvalidStateError, create_initial_state
from app.agents.macro import macro_agent_node
from app.agents.company import company_agent_node
from app.agents.quant import quant_agent_node
from app.agents.risk import risk_agent_node
from app.agents.editor import editor_agent_node


def validated_node(node_fn, name: str):
    async def wrapper(state: AgentState) -> AgentState:
        InvalidStateError().validate(state)
        return await node_fn(state)
    wrapper.__name__ = name
    return wrapper


builder = StateGraph(AgentState)

builder.add_node("macro", validated_node(macro_agent_node, "macro"))
builder.add_node("company", validated_node(company_agent_node, "company"))
builder.add_node("quant", validated_node(quant_agent_node, "quant"))
builder.add_node("risk", validated_node(risk_agent_node, "risk"))
builder.add_node("editor", validated_node(editor_agent_node, "editor"))

builder.add_edge(START, "macro")
builder.add_edge("macro", "company")
builder.add_edge("macro", "quant")
builder.add_edge("company", "risk")
builder.add_edge("quant", "risk")
builder.add_edge("risk", "editor")
builder.add_edge("editor", END)


async def create_graph() -> CompiledStateGraph:
    """Create the compiled graph with async Postgres checkpointer."""
    dsn = str(engine.url).replace("postgresql+asyncpg://", "postgresql://")
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
        return builder.compile(checkpointer=saver)


dev_graph = builder.compile(checkpointer=InMemorySaver())

__all__ = ["create_graph", "dev_graph", "create_initial_state"]
