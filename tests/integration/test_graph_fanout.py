"""Integration tests for graph fan-out with Send API."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.session as db_session
from app.agents.company import company_agent_node
from app.agents.consolidate import consolidate_node
from app.agents.editor import editor_agent_node
from app.agents.macro import macro_agent_node
from app.agents.quant import quant_agent_node
from app.agents.risk import risk_agent_node
from app.graph.serialization import get_serializer
from app.graph.state import AgentState, InvalidStateError, create_initial_state_multi

DB_URL = "postgresql+asyncpg://finagent:password@localhost:5434/finagent"


async def _run_test_with_engine(test_func):
    """Run a test with its own engine, ensuring proper cleanup in the same event loop."""
    engine = create_async_engine(
        "postgresql+asyncpg://finagent:password@localhost:5434/finagent",
        echo=False,
        pool_pre_ping=True,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    # Patch the global SessionLocal for this test
    original_session_local = db_session.SessionLocal
    db_session.SessionLocal = SessionLocal

    try:
        await test_func(SessionLocal)
    finally:
        db_session.SessionLocal = original_session_local
        await engine.dispose()


def fan_out_company(state: AgentState) -> list[Send]:
    """Fan out to company agent for each ticker."""
    base = {k: v for k, v in state.items() if k != "company_tickers"}
    return [
        Send("company", {**base, "current_ticker": t, "company_tickers": [t]})
        for t in state["company_tickers"]
    ]


def fan_out_quant(state: AgentState) -> list[Send]:
    """Fan out to quant agent for each ticker."""
    base = {k: v for k, v in state.items() if k != "company_tickers"}
    return [
        Send("quant", {**base, "current_ticker": t, "company_tickers": [t]})
        for t in state["company_tickers"]
    ]


def fan_out_risk(state: AgentState) -> list[Send]:
    """Fan out to risk agent for each ticker."""
    base = {k: v for k, v in state.items() if k != "company_tickers"}
    return [
        Send("risk", {**base, "current_ticker": t, "company_tickers": [t]})
        for t in state["company_tickers"]
    ]


def validated_node(node_fn, name: str):
    async def wrapper(state: AgentState) -> AgentState:
        InvalidStateError().validate(state)
        return await node_fn(state)
    wrapper.__name__ = name
    return wrapper


async def mock_persist_node(state: AgentState) -> dict:
    """Mock persist node - returns success without DB write."""
    return {
        "recommendation_id": 1,
        "decision_channel": None,
        "data_freshness": {"persist": datetime.now(UTC)},
        "flags": []
    }


async def mock_send_node(state: AgentState) -> dict:
    """Mock send node."""
    return {
        "data_freshness": {"send": datetime.now(UTC)},
        "flags": []
    }


async def mock_approval_gate_node(state: AgentState) -> dict:
    """Mock approval gate node."""
    return {
        "data_freshness": {"approval_gate": datetime.now(UTC)},
        "flags": []
    }


async def mock_finalize_node(state: AgentState) -> dict:
    """Mock finalize node."""
    return {
        "data_freshness": {"finalize": datetime.now(UTC)},
        "flags": []
    }


async def _build_test_graph(SessionLocal):
    """Build test graph with mocked downstream nodes (no DB access)."""

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

    # Mocked downstream nodes
    builder.add_node("persist", validated_node(mock_persist_node, "persist"))
    builder.add_node("send", validated_node(mock_send_node, "send"))
    builder.add_node("approval_gate", validated_node(mock_approval_gate_node, "approval_gate"))
    builder.add_node("finalize", validated_node(mock_finalize_node, "finalize"))

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

    checkpointer = InMemorySaver()
    checkpointer.serde = get_serializer()
    return builder.compile(checkpointer=checkpointer)


# Common mock return value for editor
EDITOR_MOCK_RETURN = '{"morning_note": "Test note", "recommendation": {"action": "buy", "justification": "Test", "confidence": 0.8}, "confidence_scores": {"macro": 0.8, "company": 0.7, "quant": 0.9, "risk": 0.6, "overall": 0.75}}'


@pytest.mark.asyncio
@pytest.mark.serial
async def test_fanout_company_quant_risk_parallel():
    """Graph runs Company, Quant, Risk in parallel per ticker using Send API."""
    async def _test(SessionLocal):

        # Setup test data in DB (for consolidate node which queries companies table)
        async with SessionLocal() as session:
            from sqlalchemy import delete, insert

            from app.db.models import Company, Manager, Portfolio, PortfolioHolding
            # Clean up ALL test data first
            await session.execute(delete(PortfolioHolding))
            await session.execute(delete(Portfolio))
            await session.execute(delete(Company))
            await session.execute(delete(Manager))
            await session.commit()

            # Insert test data
            await session.execute(insert(Manager).values(id=1, name="Test", email="test@test.com", password_hash="hash"))
            await session.execute(insert(Company).values(id=1, ticker="PETR4", name="Petrobras", sector="Energy"))
            await session.execute(insert(Company).values(id=2, ticker="VALE3", name="Vale", sector="Materials"))
            await session.execute(insert(Portfolio).values(id=1, manager_id=1, name="Test Portfolio"))
            await session.execute(insert(PortfolioHolding).values(portfolio_id=1, company_id=1, weight=0.5))
            await session.execute(insert(PortfolioHolding).values(portfolio_id=1, company_id=2, weight=0.5))
            await session.commit()

        # Build test graph
        test_graph = await _build_test_graph(SessionLocal)

        initial_state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4", "VALE3"],
            pipeline_run_id="test-run-1",
            morning_note_id="test-note-1"
        )

        # Mock external services
        with patch("app.services.tavily.TavilyService") as MockTavily, \
             patch("app.agents.macro.summarize", new=AsyncMock(return_value="Macro summary")), \
             patch("app.services.tavily.TavilyService") as MockCompanyTavily, \
             patch("app.agents.company.summarize", new=AsyncMock(return_value="Company summary")), \
             patch("app.services.yfinance.YfinanceService") as MockYfinance, \
             patch("app.agents.risk.summarize", new=AsyncMock(return_value='[{"probability": 0.5, "impact": "medium", "description": "Risk", "severity": "info"}]')), \
             patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_MOCK_RETURN)):

            # Mock Tavily for macro
            mock_tavily = MockTavily.return_value
            mock_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

            # Mock Tavily for company
            mock_company_tavily = MockCompanyTavily.return_value
            mock_company_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

            # Mock Yfinance for quant
            from app.services.yfinance import QuoteMetrics, YfinanceResult
            mock_yfinance = MockYfinance.return_value
            mock_yfinance.search = AsyncMock(return_value=YfinanceResult(
                metrics=QuoteMetrics(
                    pl=10.0, ev_ebitda=8.0, p_vpa=1.0,
                    dividend_yield=0.05, dev_ibov=0.0,
                    fetched_at=datetime.now(UTC).isoformat(),
                    market_time=datetime.now(UTC)
                ),
                error=None
            ))

            # Execute graph
            config = {"configurable": {"thread_id": "test-thread-1"}}
            result = await test_graph.ainvoke(initial_state, config=config)

            # Verify per-ticker state was merged
            assert "PETR4" in result["company_events"]
            assert "VALE3" in result["company_events"]
            assert "PETR4" in result["quant_metrics"]
            assert "VALE3" in result["quant_metrics"]
            assert "PETR4" in result["risk_flags"]
            assert "VALE3" in result["risk_flags"]

    await _run_test_with_engine(_test)


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_node_executes_after_risk():
    """Consolidate node runs after risk agents complete."""
    async def _test(SessionLocal):
        initial_state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4", "VALE3"],
            pipeline_run_id="test-run-2",
            morning_note_id="test-note-2"
        )

        with patch("app.services.tavily.TavilyService") as MockTavily, \
             patch("app.agents.macro.summarize", new=AsyncMock(return_value="Macro summary")), \
             patch("app.services.tavily.TavilyService") as MockCompanyTavily, \
             patch("app.agents.company.summarize", new=AsyncMock(return_value="Company summary")), \
             patch("app.services.yfinance.YfinanceService") as MockYfinance, \
             patch("app.agents.risk.summarize", new=AsyncMock(return_value='[{"probability": 0.5, "impact": "medium", "description": "Risk", "severity": "info"}]')), \
             patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_MOCK_RETURN)):

            mock_tavily = MockTavily.return_value
            mock_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

            mock_company_tavily = MockCompanyTavily.return_value
            mock_company_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

            from app.services.yfinance import QuoteMetrics, YfinanceResult
            mock_yfinance = MockYfinance.return_value
            mock_yfinance.search = AsyncMock(return_value=YfinanceResult(
                metrics=QuoteMetrics(
                    pl=10.0, ev_ebitda=8.0, p_vpa=1.0,
                    dividend_yield=0.05, dev_ibov=0.0,
                    fetched_at=datetime.now(UTC).isoformat(),
                    market_time=datetime.now(UTC)
                ),
                error=None
            ))

            test_graph = await _build_test_graph(SessionLocal)

            config = {"configurable": {"thread_id": "test-thread-2"}}
            result = await test_graph.ainvoke(initial_state, config=config)

            # Verify consolidate node executed
            assert "sector_weights" in result
            assert "portfolio_risk_flags" in result
            assert "portfolio_data_flags" in result
            assert "Energy" in result["sector_weights"] or "Materials" in result["sector_weights"]

    await _run_test_with_engine(_test)


@pytest.mark.asyncio
@pytest.mark.serial
async def test_editor_receives_consolidated_state():
    """Editor node receives full state with per-ticker + portfolio fields."""
    async def _test(SessionLocal):
        initial_state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4"],
            pipeline_run_id="test-run-3",
            morning_note_id="test-note-3"
        )

        with patch("app.services.tavily.TavilyService") as MockTavily, \
             patch("app.agents.macro.summarize", new=AsyncMock(return_value="Macro summary")), \
             patch("app.services.tavily.TavilyService") as MockCompanyTavily, \
             patch("app.agents.company.summarize", new=AsyncMock(return_value="Company summary")), \
             patch("app.services.yfinance.YfinanceService") as MockYfinance, \
             patch("app.agents.risk.summarize", new=AsyncMock(return_value='[{"probability": 0.5, "impact": "medium", "description": "Risk", "severity": "info"}]')), \
             patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_MOCK_RETURN)):

            mock_tavily = MockTavily.return_value
            mock_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

            mock_company_tavily = MockCompanyTavily.return_value
            mock_company_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

            from app.services.yfinance import QuoteMetrics, YfinanceResult
            mock_yfinance = MockYfinance.return_value
            mock_yfinance.search = AsyncMock(return_value=YfinanceResult(
                metrics=QuoteMetrics(
                    pl=10.0, ev_ebitda=8.0, p_vpa=1.0,
                    dividend_yield=0.05, dev_ibov=0.0,
                    fetched_at=datetime.now(UTC).isoformat(),
                    market_time=datetime.now(UTC)
                ),
                error=None
            ))

            test_graph = await _build_test_graph(SessionLocal)

            config = {"configurable": {"thread_id": "test-thread-3"}}
            result = await test_graph.ainvoke(initial_state, config=config)

            # Verify editor output is dict-keyed
            assert "PETR4" in result["recommendations"]
            assert "PETR4" in result["confidence_scores"]
            assert "Test note" in result["morning_note"]

    await _run_test_with_engine(_test)


@pytest.mark.asyncio
@pytest.mark.serial
async def test_single_ticker_still_works():
    """Graph works correctly with single ticker (backward compatibility)."""
    async def _test(SessionLocal):
        initial_state = create_initial_state_multi(
            manager_id=1,
            company_tickers=["PETR4"],
            pipeline_run_id="test-run-4",
            morning_note_id="test-note-4"
        )

        with patch("app.services.tavily.TavilyService") as MockTavily, \
             patch("app.agents.macro.summarize", new=AsyncMock(return_value="Macro summary")), \
             patch("app.services.tavily.TavilyService") as MockCompanyTavily, \
             patch("app.agents.company.summarize", new=AsyncMock(return_value="Company summary")), \
             patch("app.services.yfinance.YfinanceService") as MockYfinance, \
             patch("app.agents.risk.summarize", new=AsyncMock(return_value='[{"probability": 0.5, "impact": "medium", "description": "Risk", "severity": "info"}]')), \
             patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value=EDITOR_MOCK_RETURN)):

            mock_tavily = MockTavily.return_value
            mock_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

            mock_company_tavily = MockCompanyTavily.return_value
            mock_company_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

            from app.services.yfinance import QuoteMetrics, YfinanceResult
            mock_yfinance = MockYfinance.return_value
            mock_yfinance.search = AsyncMock(return_value=YfinanceResult(
                metrics=QuoteMetrics(
                    pl=10.0, ev_ebitda=8.0, p_vpa=1.0,
                    dividend_yield=0.05, dev_ibov=0.0,
                    fetched_at=datetime.now(UTC).isoformat(),
                    market_time=datetime.now(UTC)
                ),
                error=None
            ))

            test_graph = await _build_test_graph(SessionLocal)

            config = {"configurable": {"thread_id": "test-thread-4"}}
            result = await test_graph.ainvoke(initial_state, config=config)

            assert "PETR4" in result["company_events"]
            assert "PETR4" in result["quant_metrics"]
            assert "PETR4" in result["risk_flags"]
            assert "PETR4" in result["recommendations"]
            assert "PETR4" in result["confidence_scores"]
            assert "PETR4" in result["morning_note"]

    await _run_test_with_engine(_test)
