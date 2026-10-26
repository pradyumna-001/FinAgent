import json
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.state import InvalidStateError, create_initial_state
from app.services.tavily import TavilyArticle, TavilyResult
from app.services.yfinance import QuoteMetrics, YfinanceResult
from app.utils.flags import DataFlag, Severity


@pytest.fixture(scope="module")
def dev_graph():
    """Import dev_graph with psycopg/langgraph.checkpoint.postgres mocked."""
    originals = {
        "psycopg": sys.modules.get("psycopg"),
        "psycopg.pq": sys.modules.get("psycopg.pq"),
        "langgraph.checkpoint.postgres": sys.modules.get("langgraph.checkpoint.postgres"),
        "langgraph.checkpoint.postgres.aio": sys.modules.get("langgraph.checkpoint.postgres.aio"),
    }

    sys.modules["psycopg"] = MagicMock()
    sys.modules["psycopg.pq"] = MagicMock()
    sys.modules["langgraph.checkpoint.postgres"] = MagicMock()
    sys.modules["langgraph.checkpoint.postgres.aio"] = MagicMock()

    from app.graph.pipeline import dev_graph

    yield dev_graph

    # Restore
    for name, original in originals.items():
        if original is not None:
            sys.modules[name] = original
        else:
            sys.modules.pop(name, None)


THREAD_ID = "graph-test"

EDITOR_JSON = json.dumps({
    "morning_note": "Morning note candidate text.",
    "recommendation": {
        "action": "buy",
        "justification": "Strong upward signals.",
        "confidence": 0.8
    },
    "confidence_scores": {
        "macro": 0.9,
        "company": 0.85,
        "quant": 0.88,
        "risk": 0.82,
        "overall": 0.86
    }
})


def make_state(manager_id: int = 1, ticker: str = "PETR4"):
    return create_initial_state(
        manager_id=manager_id,
        company_ticker=ticker,
        pipeline_run_id="run-1",
        morning_note_id="note-1"
    )


def _tavily_ok():
    return TavilyResult(
        articles=[TavilyArticle(
            title="Title",
            content="Body text.",
            url="https://example.test",
        )],
        error=None,
    )


def _quant_ok():
    return YfinanceResult(
        metrics=QuoteMetrics(
            pl=8.0, ev_ebitda=6.5, p_vpa=1.2,
            dividend_yield=0.05, dev_ibov=-0.01,
            fetched_at=datetime.now(UTC).isoformat(),
            market_time=datetime.now(UTC),
        ),
        error=None,
    )


@pytest.fixture
def patched_services():
    """Patch external services (Tavily, Yfinance, LLM summarizers)."""
    with (
        patch("app.agents.macro.TavilyService") as MacroT,
        patch("app.agents.company.TavilyService") as CompT,
        patch("app.agents.quant.YfinanceService") as Yf,
        patch("app.agents.macro.summarize", new=AsyncMock(return_value="mac")),
        patch("app.agents.company.summarize", new=AsyncMock(return_value="comp")),
        patch("app.agents.risk.summarize", new=AsyncMock(return_value="[{}]")),
        patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_JSON)),
    ):
        MacroT.return_value.search = AsyncMock(return_value=_tavily_ok())
        CompT.return_value.search = AsyncMock(return_value=_tavily_ok())
        Yf.return_value.search = AsyncMock(return_value=_quant_ok())
        yield


@pytest.fixture
def test_graph(dev_graph, patched_services):
    """Create a test graph with persist_recommendation_node mocked to avoid DB."""
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from app.graph.state import AgentState, InvalidStateError
    from app.agents.company import company_agent_node
    from app.agents.editor import editor_agent_node
    from app.agents.macro import macro_agent_node
    from app.agents.quant import quant_agent_node
    from app.agents.risk import risk_agent_node
    from app.agents.send import send_note_node
    from app.agents.approval_gate import approval_gate_node

    def validated_node(node_fn, name: str):
        async def wrapper(state: AgentState) -> AgentState:
            InvalidStateError().validate(state)
            return await node_fn(state)
        wrapper.__name__ = name
        return wrapper

    # Mock persist node to avoid database
    mock_persist = AsyncMock(return_value={
        "recommendation_id": 1,
        "decision_channel": None,
        "data_freshness": {"persist": datetime.now(UTC)},
        "flags": []
    })

    builder = StateGraph(AgentState)
    builder.add_node("macro", validated_node(macro_agent_node, "macro"))
    builder.add_node("company", validated_node(company_agent_node, "company"))
    builder.add_node("quant", validated_node(quant_agent_node, "quant"))
    builder.add_node("risk", validated_node(risk_agent_node, "risk"))
    builder.add_node("editor", validated_node(editor_agent_node, "editor"))
    builder.add_node("persist", validated_node(mock_persist, "persist"))
    builder.add_node("send", validated_node(send_note_node, "send"))
    builder.add_node("approval_gate", validated_node(approval_gate_node, "approval_gate"))

    builder.add_edge(START, "macro")
    builder.add_edge("macro", "company")
    builder.add_edge("macro", "quant")
    builder.add_edge("company", "risk")
    builder.add_edge("quant", "risk")
    builder.add_edge("risk", "editor")
    builder.add_edge("editor", "persist")
    builder.add_edge("persist", "send")
    builder.add_edge("send", "approval_gate")
    builder.add_edge("approval_gate", END)

    return builder.compile(checkpointer=InMemorySaver())


@pytest.mark.asyncio
async def test_validate_state_rejects_invalid(test_graph):
    bad_state = make_state(manager_id=0)
    with pytest.raises(InvalidStateError):
        await test_graph.ainvoke(bad_state, config={"configurable": {"thread_id": THREAD_ID}})


@pytest.mark.asyncio
async def test_confidence_scores_populated(test_graph, patched_services):
    result = await test_graph.ainvoke(make_state(), config={"configurable": {"thread_id": THREAD_ID}})
    scores = result["confidence_scores"]
    assert set(scores.keys()) == {"macro", "company", "quant", "risk", "overall"}
    assert all(isinstance(v, float) for v in scores.values())


@pytest.mark.asyncio
async def test_parallel_execution(test_graph, patched_services):
    from app.utils.flags import DataFlag, Severity

    with patch("app.agents.company.TavilyService") as CompT:
        CompT.return_value.search = AsyncMock(return_value=TavilyResult(
            articles=[], error=DataFlag(source="tavily", severity=Severity.WARNING, message="company fail")
        ))
        with patch("app.agents.quant.YfinanceService") as Yf:
            from app.services.yfinance import YfinanceResult
            Yf.return_value.search = AsyncMock(return_value=YfinanceResult(
                metrics=None,
                error=DataFlag(source="yfinance", severity=Severity.WARNING, message="quant fail")
            ))
            result = await test_graph.ainvoke(make_state(), config={"configurable": {"thread_id": THREAD_ID}})

    flags = result["flags"]
    assert any(f.source == "tavily" for f in flags), "company flag lost in merge"
    assert any(f.source == "yfinance" for f in flags), "quant flag lost in merge"

    cf = result["data_freshness"]["company"]
    qf = result["data_freshness"]["quant"]
    assert abs((cf - qf).total_seconds()) < 1.0, "parallel timestamps diverged"


@pytest.mark.asyncio
async def test_fail_visible_invariant(test_graph, patched_services):
    with patch("app.agents.company.TavilyService") as CompT:
        CompT.return_value.search = AsyncMock(return_value=TavilyResult(
            articles=[], error=DataFlag(source="tavily", severity=Severity.WARNING, message="company fail")
        ))
        result = await test_graph.ainvoke(make_state(), config={"configurable": {"thread_id": THREAD_ID}})

    note = result["morning_note"]
    assert "[Aviso]: company - dados incompletos ou falhos" in note