#!/usr/bin/env python
"""Standalone test runner for full multi-ticker graph execution using existing PostgreSQL."""

import asyncio
import os
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Use environment variables for DB URLs (set in CI), default to local PostgreSQL on 5434
migration_db_url = os.environ.get("MIGRATION_DATABASE_URL", "postgresql+psycopg://finagent:password@localhost:5434/finagent")
db_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://finagent:password@localhost:5434/finagent")
os.environ["MIGRATION_DATABASE_URL"] = migration_db_url
os.environ["DATABASE_URL"] = db_url

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.types import Send  # noqa: E402
from sqlalchemy import delete, insert  # noqa: E402

from app.agents.company import company_agent_node  # noqa: E402
from app.agents.consolidate import consolidate_node  # noqa: E402
from app.agents.editor import editor_agent_node  # noqa: E402
from app.agents.macro import macro_agent_node  # noqa: E402
from app.agents.quant import quant_agent_node  # noqa: E402
from app.agents.risk import risk_agent_node  # noqa: E402
from app.db.models import Company, Manager, Portfolio, PortfolioHolding  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.graph.serialization import get_serializer  # noqa: E402
from app.graph.state import AgentState, InvalidStateError, create_initial_state_multi  # noqa: E402


async def setup_test_data():
    """Insert test data: manager, companies, portfolio, holdings."""
    async with SessionLocal() as session:
        # Clean up existing test data
        await session.execute(delete(PortfolioHolding).where(PortfolioHolding.portfolio_id == 999))
        await session.execute(delete(Portfolio).where(Portfolio.id == 999))
        await session.execute(delete(Company).where(Company.ticker.in_(["PETR4", "VALE3", "ITUB4"])))
        await session.execute(delete(Manager).where(Manager.id == 999))

        # Insert test data with explicit IDs
        await session.execute(insert(Manager).values(id=999, name="Test Manager", email="test@test.com", password_hash="hash"))
        await session.execute(insert(Company).values(id=1, ticker="PETR4", name="Petrobras", sector="Energy"))
        await session.execute(insert(Company).values(id=2, ticker="VALE3", name="Vale", sector="Materials"))
        await session.execute(insert(Company).values(id=3, ticker="ITUB4", name="Itau", sector="Financial"))
        await session.execute(insert(Portfolio).values(id=999, manager_id=999, name="Test Portfolio"))
        await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=1, weight=0.4))  # PETR4
        await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=2, weight=0.3))  # VALE3
        await session.execute(insert(PortfolioHolding).values(portfolio_id=999, company_id=3, weight=0.3))  # ITUB4
        await session.commit()


async def setup_single_ticker_test_data():
    """Insert test data for single ticker test."""
    async with SessionLocal() as session:
        # Clean up ALL test data from both tests
        await session.execute(delete(PortfolioHolding).where(PortfolioHolding.portfolio_id.in_([999, 998])))
        await session.execute(delete(Portfolio).where(Portfolio.id.in_([999, 998])))
        await session.execute(delete(Company).where(Company.ticker.in_(["PETR4", "VALE3", "ITUB4"])))
        await session.execute(delete(Manager).where(Manager.id.in_([999, 998])))

        await session.execute(insert(Manager).values(id=998, name="Test Manager 2", email="test2@test.com", password_hash="hash"))
        await session.execute(insert(Company).values(id=10, ticker="PETR4", name="Petrobras", sector="Energy"))
        await session.execute(insert(Portfolio).values(id=998, manager_id=998, name="Test Portfolio 2"))
        await session.execute(insert(PortfolioHolding).values(portfolio_id=998, company_id=10, weight=1.0))
        await session.commit()


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


async def build_test_graph():
    """Build the full fan-out graph with mocked downstream nodes."""
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


async def run_full_graph_test():
    """Run full multi-ticker graph execution test."""
    print("=" * 70)
    print("FULL MULTI-TICKER GRAPH EXECUTION TEST")
    print("=" * 70)

    # Setup test data
    print("\n1. Setting up test data...")
    await setup_test_data()
    print("   Test data inserted: Manager(999), 3 Companies, Portfolio(999) with 3 holdings")

    # Create initial state with 3 tickers
    initial_state = create_initial_state_multi(
        manager_id=999,
        company_tickers=["PETR4", "VALE3", "ITUB4"],
        pipeline_run_id="test-full-graph-1",
        morning_note_id="test-note-1"
    )
    print(f"   Initial state created with tickers: {initial_state['company_tickers']}")

    # Build graph with mocked downstream nodes
    print("\n2. Building graph with mocked downstream nodes...")
    graph = await build_test_graph()

    # Mock external services
    print("\n3. Mocking external services...")
    with patch("app.agents.macro.TavilyService") as MockTavily, \
         patch("app.agents.macro.summarize", new=AsyncMock(return_value="Macro summary: Selic at 13.75%, IBOV up 2%")), \
         patch("app.agents.company.TavilyService") as MockCompanyTavily, \
         patch("app.agents.company.summarize", new=AsyncMock(return_value="Company news summary")), \
         patch("app.agents.quant.YfinanceService") as MockYfinance, \
         patch("app.agents.risk.summarize", new=AsyncMock(return_value='[{"probability": 0.6, "impact": "medium", "description": "Concentration risk in Energy", "severity": "warning"}]')), \
         patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value='{"morning_note": "Test morning note for {ticker}", "recommendation": {"action": "buy", "justification": "Strong fundamentals", "confidence": 0.8}, "confidence_scores": {"macro": 0.85, "company": 0.8, "quant": 0.9, "risk": 0.75, "overall": 0.82}}')):

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
                pl=8.5, ev_ebitda=6.2, p_vpa=1.1,
                dividend_yield=0.08, dev_ibov=0.02,
                fetched_at=datetime.now(UTC).isoformat(),
                market_time=datetime.now(UTC)
            ),
            error=None
        ))

        # Execute graph
        print("\n4. Executing full graph...")
        config = {"configurable": {"thread_id": "test-full-graph-thread-1"}}
        result = await graph.ainvoke(initial_state, config=config)

        # Verify results
        print("\n5. Verifying results...")

        # Macro ran once
        assert "macro_context" in result, "macro_context missing"
        assert "global" in result["macro_context"], "macro_context.global missing"
        print("   [OK] Macro ran once, macro_context.global present")

        # Per-ticker state merged via merge_dicts
        assert "PETR4" in result["company_events"], "PETR4 missing from company_events"
        assert "VALE3" in result["company_events"], "VALE3 missing from company_events"
        assert "ITUB4" in result["company_events"], "ITUB4 missing from company_events"
        print("   [OK] Company events merged for all 3 tickers")

        assert "PETR4" in result["quant_metrics"], "PETR4 missing from quant_metrics"
        assert "VALE3" in result["quant_metrics"], "VALE3 missing from quant_metrics"
        assert "ITUB4" in result["quant_metrics"], "ITUB4 missing from quant_metrics"
        print("   [OK] Quant metrics merged for all 3 tickers")

        assert "PETR4" in result["risk_flags"], "PETR4 missing from risk_flags"
        assert "VALE3" in result["risk_flags"], "VALE3 missing from risk_flags"
        assert "ITUB4" in result["risk_flags"], "ITUB4 missing from risk_flags"
        print("   [OK] Risk flags merged for all 3 tickers")

        # Consolidate ran
        assert "sector_weights" in result, "sector_weights missing"
        assert "Energy" in result["sector_weights"], "Energy sector missing"
        assert "Materials" in result["sector_weights"], "Materials sector missing"
        assert "Financial" in result["sector_weights"], "Financial sector missing"
        print(f"   [OK] Consolidate ran: sector_weights = {result['sector_weights']}")

        assert "portfolio_risk_flags" in result, "portfolio_risk_flags missing"
        assert "portfolio_data_flags" in result, "portfolio_data_flags missing"
        print("   [OK] Portfolio risk/data flags present")

        # Editor ran with per-ticker output
        assert "recommendations" in result, "recommendations missing"
        assert "PETR4" in result["recommendations"], "PETR4 missing from recommendations"
        assert "VALE3" in result["recommendations"], "VALE3 missing from recommendations"
        assert "ITUB4" in result["recommendations"], "ITUB4 missing from recommendations"
        print("   [OK] Editor produced per-ticker recommendations")

        assert "confidence_scores" in result, "confidence_scores missing"
        assert "PETR4" in result["confidence_scores"], "PETR4 missing from confidence_scores"
        assert "VALE3" in result["confidence_scores"], "VALE3 missing from confidence_scores"
        assert "ITUB4" in result["confidence_scores"], "ITUB4 missing from confidence_scores"
        print("   [OK] Editor produced per-ticker confidence scores")

        assert "morning_note" in result, "morning_note missing"
        assert isinstance(result["morning_note"], str), "morning_note not string"
        assert "PETR4" in result["morning_note"], "PETR4 not in morning_note"
        assert "VALE3" in result["morning_note"], "VALE3 not in morning_note"
        assert "ITUB4" in result["morning_note"], "ITUB4 not in morning_note"
        print(f"   [OK] Consolidated morning_note generated ({len(result['morning_note'])} chars)")

        # Data freshness
        assert "data_freshness" in result, "data_freshness missing"
        assert "macro" in result["data_freshness"], "macro freshness missing"
        assert "PETR4" in result["data_freshness"], "PETR4 freshness missing"
        print("   [OK] Data freshness tracked for all sources")

        print("\n" + "=" * 70)
        print("ALL ASSERTIONS PASSED - FULL GRAPH EXECUTION TEST SUCCESSFUL")
        print("=" * 70)
        return True


async def run_single_ticker_test():
    """Test that single ticker still works (backward compatibility)."""
    print("\n" + "=" * 70)
    print("SINGLE TICKER BACKWARD COMPATIBILITY TEST")
    print("=" * 70)

    # Setup test data
    print("\n1. Setting up test data...")
    await setup_single_ticker_test_data()
    print("   Test data inserted: Manager(998), 1 Company, Portfolio(998)")

    # Create initial state with single ticker
    initial_state = create_initial_state_multi(
        manager_id=998,
        company_tickers=["PETR4"],
        pipeline_run_id="test-single-1",
        morning_note_id="test-note-single-1"
    )
    print(f"   Initial state created with tickers: {initial_state['company_tickers']}")

    # Build graph with mocked downstream nodes
    graph = await build_test_graph()

    # Mock external services
    print("\n2. Mocking external services...")
    with patch("app.agents.macro.TavilyService") as MockTavily, \
         patch("app.agents.macro.summarize", new=AsyncMock(return_value="Macro summary")), \
         patch("app.agents.company.TavilyService") as MockCompanyTavily, \
         patch("app.agents.company.summarize", new=AsyncMock(return_value="Company summary")), \
         patch("app.agents.quant.YfinanceService") as MockYfinance, \
         patch("app.agents.risk.summarize", new=AsyncMock(return_value='[{"probability": 0.5, "impact": "medium", "description": "Risk", "severity": "info"}]')), \
         patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value='{"morning_note": "Single ticker note", "recommendation": {"action": "buy", "justification": "Test", "confidence": 0.8}, "confidence_scores": {"macro": 0.8, "company": 0.7, "quant": 0.9, "risk": 0.6, "overall": 0.75}}')):

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
        print("\n3. Executing single ticker graph...")
        config = {"configurable": {"thread_id": "test-single-thread-1"}}
        result = await graph.ainvoke(initial_state, config=config)

        # Verify results
        assert "PETR4" in result["company_events"]
        assert "PETR4" in result["quant_metrics"]
        assert "PETR4" in result["risk_flags"]
        assert "PETR4" in result["recommendations"]
        assert "PETR4" in result["confidence_scores"]
        assert "PETR4" in result["morning_note"]
        print("   [OK] Single ticker graph execution works")

        print("\n" + "=" * 70)
        print("SINGLE TICKER TEST PASSED")
        print("=" * 70)
        return True


async def main():
    try:
        await run_full_graph_test()
        await run_single_ticker_test()
        print("\nALL TESTS PASSED!")
        return 0
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
