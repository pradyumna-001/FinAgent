import sys
from unittest.mock import MagicMock, AsyncMock, patch

from app.utils.flags import DataFlag, Severity

# Mock psycopg/libpq before app.graph.pipeline imports it
sys.modules["psycopg"] = MagicMock()
sys.modules["psycopg.pq"] = MagicMock()
sys.modules["langgraph.checkpoint.postgres"] = MagicMock()
sys.modules["langgraph.checkpoint.postgres.aio"] = MagicMock()

import json  # noqa: E402
import pytest  # noqa: E402

from datetime import datetime, UTC  # noqa: E402
from app.services.tavily import TavilyArticle, TavilyResult  # noqa: E402
from app.services.yfinance import QuoteMetrics, YfinanceResult  # noqa: E402
from app.graph.pipeline import dev_graph  # noqa: E402
from app.graph.state import create_initial_state, InvalidStateError  # noqa: E402

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
def patched_pipeline():
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


@pytest.mark.asyncio
async def test_validate_state_rejects_invalid():
    bad_state = make_state(manager_id=0)  # invalid: not positive
    with pytest.raises(InvalidStateError):
        await dev_graph.ainvoke(bad_state, config={"configurable": {"thread_id": THREAD_ID}})


@pytest.mark.asyncio
async def test_confidence_scores_populated(patched_pipeline):
    result = await dev_graph.ainvoke(make_state(), config={"configurable": {"thread_id": THREAD_ID}})
    scores = result["confidence_scores"]
    assert set(scores.keys()) == {"macro", "company", "quant", "risk", "overall"}
    assert all(isinstance(v, float) for v in scores.values())


@pytest.mark.asyncio
async def test_parallel_execution(patched_pipeline):
    from app.utils.flags import DataFlag, Severity

    # Override company Tavily to return an error flag
    with patch("app.agents.company.TavilyService") as CompT:
        CompT.return_value.search = AsyncMock(return_value=TavilyResult(
            articles=[], error=DataFlag(source="tavily", severity=Severity.WARNING, message="company fail")
        ))
        # Override quant Yfinance to return an error flag
        with patch("app.agents.quant.YfinanceService") as Yf:
            from app.services.yfinance import YfinanceResult
            Yf.return_value.search = AsyncMock(return_value=YfinanceResult(
                metrics=None,
                error=DataFlag(source="yfinance", severity=Severity.WARNING, message="quant fail")
            ))
            result = await dev_graph.ainvoke(make_state(), config={"configurable": {"thread_id": THREAD_ID}})

    flags = result["flags"]
    assert any(f.source == "tavily" for f in flags), "company flag lost in merge"
    assert any(f.source == "yfinance" for f in flags), "quant flag lost in merge"

    # Both data_freshness timestamps should be set and close together (within 1s)
    cf = result["data_freshness"]["company"]
    qf = result["data_freshness"]["quant"]
    assert abs((cf - qf).total_seconds()) < 1.0, "parallel timestamps diverged"


@pytest.mark.asyncio
async def test_fail_visible_invariant(patched_pipeline):
    with patch("app.agents.company.TavilyService") as CompT:
        CompT.return_value.search = AsyncMock(return_value=TavilyResult(
            articles=[], error=DataFlag(source="tavily", severity=Severity.WARNING, message="company fail")
        ))
        result = await dev_graph.ainvoke(make_state(), config={"configurable": {"thread_id": THREAD_ID}})

    note = result["morning_note"]
    assert "[Aviso]: company - dados incompletos ou falhos" in note


