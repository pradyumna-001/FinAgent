"""Integration tests for graph fan-out with Send API."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import insert

from app.db.models import Company, Manager, Portfolio, PortfolioHolding
from app.db.session import SessionLocal
from app.graph.pipeline import compile_graph
from app.graph.state import create_initial_state_multi


@pytest.mark.asyncio
@pytest.mark.serial
async def test_graph_compiles_with_fanout(migrated_db_url: str):
    """Graph compiles successfully with fan-out structure."""
    from langgraph.checkpoint.memory import InMemorySaver
    checkpointer = InMemorySaver()
    graph = compile_graph(checkpointer)
    assert graph is not None


@pytest.mark.asyncio
@pytest.mark.serial
async def test_fanout_company_quant_risk_parallel(migrated_db_url: str):
    """Graph runs Company, Quant, Risk in parallel per ticker using Send API."""
    from langgraph.checkpoint.memory import InMemorySaver
    checkpointer = InMemorySaver()
    graph = compile_graph(checkpointer)

    # Setup test data
    async with SessionLocal() as session:
        await session.execute(insert(Manager).values(id=1, name="Test", email="test@test.com", password_hash="hash"))
        await session.execute(insert(Company).values(id=1, ticker="PETR4", name="Petrobras"))
        await session.execute(insert(Company).values(id=2, ticker="VALE3", name="Vale"))
        await session.execute(insert(Portfolio).values(id=1, manager_id=1, name="Test Portfolio"))
        await session.execute(insert(PortfolioHolding).values(portfolio_id=1, company_id=1, weight=0.5))
        await session.execute(insert(PortfolioHolding).values(portfolio_id=1, company_id=2, weight=0.5))
        await session.commit()

    initial_state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4", "VALE3"],
        pipeline_run_id="test-run-1",
        morning_note_id="test-note-1"
    )

    # Mock external services
    with patch("app.agents.macro.TavilyService") as MockTavily, \
         patch("app.agents.macro.summarize", new=AsyncMock(return_value="Macro summary")), \
         patch("app.agents.company.TavilyService") as MockCompanyTavily, \
         patch("app.agents.company.summarize", new=AsyncMock(return_value="Company summary")), \
         patch("app.agents.quant.YfinanceService") as MockYfinance, \
         patch("app.agents.risk.summarize", new=AsyncMock(return_value='[{"probability": 0.5, "impact": "medium", "description": "Risk", "severity": "info"}]')):

        # Mock Tavily for macro
        mock_tavily = MockTavily.return_value
        mock_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

        # Mock Tavily for company
        mock_company_tavily = MockCompanyTavily.return_value
        mock_company_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

        # Mock Yfinance for quant
        mock_yfinance = MockYfinance.return_value
        mock_yfinance.search = AsyncMock(return_value=type('obj', (object,), {'metrics': type('obj', (object,), {'pl': 10.0, 'ev_ebitda': 8.0, 'p_vpa': 1.0, 'dividend_yield': 0.05, 'dev_ibov': 0.0, 'fetched_at': '2024-01-01', 'market_time': None})(), 'error': None})())

        # Execute graph
        config = {"configurable": {"thread_id": "test-thread-1"}}
        result = await graph.ainvoke(initial_state, config=config)

        # Verify per-ticker state was merged
        assert "PETR4" in result["company_events"]
        assert "VALE3" in result["company_events"]
        assert "PETR4" in result["quant_metrics"]
        assert "VALE3" in result["quant_metrics"]
        assert "PETR4" in result["risk_flags"]
        assert "VALE3" in result["risk_flags"]


@pytest.mark.asyncio
@pytest.mark.serial
async def test_consolidate_node_executes_after_risk(migrated_db_url: str):
    """Consolidate node runs after risk agents complete."""
    from langgraph.checkpoint.memory import InMemorySaver
    checkpointer = InMemorySaver()
    graph = compile_graph(checkpointer)

    initial_state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4", "VALE3"],
        pipeline_run_id="test-run-2",
        morning_note_id="test-note-2"
    )

    with patch("app.agents.macro.TavilyService") as MockTavily, \
         patch("app.agents.macro.summarize", new=AsyncMock(return_value="Macro summary")), \
         patch("app.agents.company.TavilyService") as MockCompanyTavily, \
         patch("app.agents.company.summarize", new=AsyncMock(return_value="Company summary")), \
         patch("app.agents.quant.YfinanceService") as MockYfinance, \
         patch("app.agents.risk.summarize", new=AsyncMock(return_value='[{"probability": 0.5, "impact": "medium", "description": "Risk", "severity": "info"}]')):

        mock_tavily = MockTavily.return_value
        mock_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

        mock_company_tavily = MockCompanyTavily.return_value
        mock_company_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

        mock_yfinance = MockYfinance.return_value
        mock_yfinance.search = AsyncMock(return_value=type('obj', (object,), {'metrics': type('obj', (object,), {'pl': 10.0, 'ev_ebitda': 8.0, 'p_vpa': 1.0, 'dividend_yield': 0.05, 'dev_ibov': 0.0, 'fetched_at': '2024-01-01', 'market_time': None})(), 'error': None})())

        config = {"configurable": {"thread_id": "test-thread-2"}}
        result = await graph.ainvoke(initial_state, config=config)

        # Verify consolidate node executed
        assert "sector_weights" in result
        assert "portfolio_risk_flags" in result
        assert "portfolio_data_flags" in result
        assert "PETR4" in result["sector_weights"] or "VALE3" in result["sector_weights"]


@pytest.mark.asyncio
@pytest.mark.serial
async def test_editor_receives_consolidated_state(migrated_db_url: str):
    """Editor node receives full state with per-ticker + portfolio fields."""
    from langgraph.checkpoint.memory import InMemorySaver
    checkpointer = InMemorySaver()
    graph = compile_graph(checkpointer)

    initial_state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4"],
        pipeline_run_id="test-run-3",
        morning_note_id="test-note-3"
    )

    with patch("app.agents.macro.TavilyService") as MockTavily, \
         patch("app.agents.macro.summarize", new=AsyncMock(return_value="Macro summary")), \
         patch("app.agents.company.TavilyService") as MockCompanyTavily, \
         patch("app.agents.company.summarize", new=AsyncMock(return_value="Company summary")), \
         patch("app.agents.quant.YfinanceService") as MockYfinance, \
         patch("app.agents.risk.summarize", new=AsyncMock(return_value='[{"probability": 0.5, "impact": "medium", "description": "Risk", "severity": "info"}]')), \
         patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value='{"morning_note": "Test note", "recommendation": {"action": "buy", "justification": "Test", "confidence": 0.8}, "confidence_scores": {"macro": 0.8, "company": 0.7, "quant": 0.9, "risk": 0.6, "overall": 0.75}}')):

        mock_tavily = MockTavily.return_value
        mock_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

        mock_company_tavily = MockCompanyTavily.return_value
        mock_company_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

        mock_yfinance = MockYfinance.return_value
        mock_yfinance.search = AsyncMock(return_value=type('obj', (object,), {'metrics': type('obj', (object,), {'pl': 10.0, 'ev_ebitda': 8.0, 'p_vpa': 1.0, 'dividend_yield': 0.05, 'dev_ibov': 0.0, 'fetched_at': '2024-01-01', 'market_time': None})(), 'error': None})())

        config = {"configurable": {"thread_id": "test-thread-3"}}
        result = await graph.ainvoke(initial_state, config=config)

        # Verify editor output is dict-keyed
        assert "PETR4" in result["recommendations"]
        assert "PETR4" in result["confidence_scores"]
        assert result["morning_note"] == "Test note"


@pytest.mark.asyncio
@pytest.mark.serial
async def test_single_ticker_still_works(migrated_db_url: str):
    """Graph works correctly with single ticker (backward compatibility)."""
    from langgraph.checkpoint.memory import InMemorySaver
    checkpointer = InMemorySaver()
    graph = compile_graph(checkpointer)

    initial_state = create_initial_state_multi(
        manager_id=1,
        company_tickers=["PETR4"],
        pipeline_run_id="test-run-4",
        morning_note_id="test-note-4"
    )

    with patch("app.agents.macro.TavilyService") as MockTavily, \
         patch("app.agents.macro.summarize", new=AsyncMock(return_value="Macro summary")), \
         patch("app.agents.company.TavilyService") as MockCompanyTavily, \
         patch("app.agents.company.summarize", new=AsyncMock(return_value="Company summary")), \
         patch("app.agents.quant.YfinanceService") as MockYfinance, \
         patch("app.agents.risk.summarize", new=AsyncMock(return_value='[{"probability": 0.5, "impact": "medium", "description": "Risk", "severity": "info"}]')), \
         patch("app.agents.editor.summarize_nemotron", new=AsyncMock(return_value='{"morning_note": "Test", "recommendation": {"action": "buy", "justification": "Test", "confidence": 0.8}, "confidence_scores": {"macro": 0.8, "company": 0.7, "quant": 0.9, "risk": 0.6, "overall": 0.75}}')):

        mock_tavily = MockTavily.return_value
        mock_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

        mock_company_tavily = MockCompanyTavily.return_value
        mock_company_tavily.search = AsyncMock(return_value=type('obj', (object,), {'articles': [], 'error': None})())

        mock_yfinance = MockYfinance.return_value
        mock_yfinance.search = AsyncMock(return_value=type('obj', (object,), {'metrics': type('obj', (object,), {'pl': 10.0, 'ev_ebitda': 8.0, 'p_vpa': 1.0, 'dividend_yield': 0.05, 'dev_ibov': 0.0, 'fetched_at': '2024-01-01', 'market_time': None})(), 'error': None})())

        config = {"configurable": {"thread_id": "test-thread-4"}}
        result = await graph.ainvoke(initial_state, config=config)

        assert "PETR4" in result["company_events"]
        assert "PETR4" in result["quant_metrics"]
        assert "PETR4" in result["risk_flags"]
        assert "PETR4" in result["recommendations"]
