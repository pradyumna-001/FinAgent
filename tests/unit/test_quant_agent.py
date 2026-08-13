import logging
from datetime import datetime
from unittest.mock import patch, AsyncMock

import pytest 

from app.agents.quant import quant_agent_node
from app.graph.state import create_initial_state, DataFlag
from app.services.yfinance import QuoteMetrics, YfinanceResult
from app.utils.flags import Severity


def make_state():
    return create_initial_state(
        manager_id=1,
        company_ticker="PETR4",
        pipeline_run_id="run-1",
        morning_note_id="note-1"
    )


def _metrics(**overrides):
    base = {
        "pl": 15.2,
        "ev_ebitda": 8.1,
        "p_vpa": 1.3,
        "dividend_yield": 0.04,
        "dev_ibov": 0.08,
        "fetched_at": datetime.now().isoformat()
    }
    base.update(overrides)
    return QuoteMetrics(**base)


@pytest.mark.asyncio
async def test_quant_agent_happy_path():
    result = YfinanceResult(metrics=_metrics(), error=None)
    with patch("app.agents.quant.YfinanceService") as MockSvc:
        MockSvc.return_value.search = AsyncMock(return_value=result)
        res = await quant_agent_node(make_state())

    qm = res["quant_metrics"]

    assert qm["pl"] == 15.2
    assert qm["dev_ibov"] == 0.08
    assert isinstance(res["data_freshness"]["quant"], datetime)
    assert res["flags"] == []


@pytest.mark.asyncio
async def test_quant_agent_service_warning():
    error = DataFlag(
        source="yfinance",
        severity=Severity.WARNING,
        message="Yfinance request error: throttled"
    )
    result = YfinanceResult(metrics=None, error=error)
    with patch("app.agents.quant.YfinanceService") as MockSvc:
        MockSvc.return_value.search = AsyncMock(return_value=result)
        res = await quant_agent_node(make_state())

    assert res["quant_metrics"] is None
    assert res["flags"][-1].source == "yfinance"
    assert isinstance(res["data_freshness"]["quant"], datetime)


@pytest.mark.asyncio
async def test_quant_agent_service_fatal():
    error = DataFlag(
        source="yfinance",
        severity=Severity.FATAL,
        message="Yfinance data for 'PETR4' is 48.0h old (max 24h)"
    )
    result = YfinanceResult(metrics=None, error=error)
    with patch("app.agents.quant.YfinanceService") as MockSvc:
        MockSvc.return_value.search = AsyncMock(return_value=result)
        res = await quant_agent_node(make_state())

    assert res["quant_metrics"] is None
    assert res["flags"][-1].severity.value == "fatal"


@pytest.mark.asyncio
async def test_quant_agent_empty_ticker():
    from app.services.yfinance import YfinanceError
    with patch("app.agents.quant.YfinanceService", side_effect=YfinanceError("ticker must be non-empty")):
        res = await quant_agent_node(make_state())

    assert res["quant_metrics"] is None
    assert res["flags"][-1].severity.value == "fatal"
    assert "ticker must be non-empty" in res["flags"][-1].message


@pytest.mark.asyncio
async def test_quant_agent_logs_entry(caplog):
    result = YfinanceResult(metrics=_metrics(), error=None)
    with caplog.at_level(logging.INFO, logger="app.agents.quant"):
        with patch("app.agents.quant.YfinanceService") as MockSvc:
            MockSvc.return_value.search = AsyncMock(return_value=result)
            await quant_agent_node(make_state())

        records = [r for r in caplog.records if r.name == "app.agents.quant"]
        assert len(records) >= 1
        assert records[0].pipeline_run_id == "run-1"
        assert records[0].morning_note_id == "note-1"
        assert records[0].manager_id == 1
        