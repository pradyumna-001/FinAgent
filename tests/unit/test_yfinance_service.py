from datetime import datetime
import time
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from app.services.yfinance import YfinanceService, YfinanceError
from app.utils.flags import Severity


def _fake_info(**overrides):
    base = {
        "trailingPE": 15.2,
        "enterpriseToEbitda": 8.1,
        "priceToBook": 1.3,
        "dividendYield": 0.04,
        "regularMarketTime": int(time.time())
    }
    base.update(overrides)
    return base


def _fake_history(today_close, yesterday_close):
    return pd.DataFrame({"Close": [yesterday_close, today_close]})


def _ticker_mock(info, history):
    """Build a per-ticker mock with .info and .history.return_value set."""
    m = MagicMock()
    m.info = info
    m.history.return_value = history
    return m


def _ticker_side_effect(ticker_info, ticker_history, ibov_history):
    """Dispatch yf.Ticker(...) per-symbol — ticker ( suffixed .SA) vs market_index (^BVSP)."""
    def _side_effect(symbol, *args, **kwargs):
        if symbol.endswith(".SA"):
            return _ticker_mock(ticker_info, ticker_history)
        return _ticker_mock(_fake_info(), ibov_history)
    return _side_effect


@pytest.mark.asyncio
async def test_search_happy_path_returns_typed_metrics():
    with patch("app.services.yfinance.yf.Ticker") as MockTicker:
        MockTicker.side_effect = _ticker_side_effect(
            ticker_info=_fake_info(),
            ticker_history=_fake_history(33.0, 30.0),
            ibov_history=_fake_history(102.0, 100.0)
        )

        svc = YfinanceService(ticker="PETR4")
        result = await svc.search()

    assert result.error is None
    assert result.metrics.pl == 15.2
    assert result.metrics.ev_ebitda == 8.1
    assert result.metrics.p_vpa == 1.3
    assert result.metrics.dividend_yield == 0.04
    assert abs(result.metrics.dev_ibov - 0.08) < 1e-9
    assert result.metrics.fetched_at
    assert result.metrics.market_time is not None
    assert isinstance(result.metrics.market_time, datetime)


@pytest.mark.asyncio
async def test_search_empty_ticker_raises_yfinance_error():
    with pytest.raises(YfinanceError, match="ticker must be non-empty"):
        YfinanceService(ticker="")


@pytest.mark.asyncio
async def test_search_http_failure_returns_warning():
    with patch("app.services.yfinance.yf.Ticker") as MockTicker:
        MockTicker.return_value.info = None

        svc = YfinanceService(ticker="PETR4")
        result = await svc.search()

    assert result.metrics is None
    assert result.error.severity == Severity.WARNING
    assert "no info dict" in result.error.message


@pytest.mark.asyncio
async def test_search_no_expected_metrics_returns_fatal():
    with patch("app.services.yfinance.yf.Ticker") as MockTicker:
        MockTicker.return_value.info = {"randomKey": "x", "otherKey": None}

        svc = YfinanceService(ticker="PETR4")
        result = await svc.search()

    assert result.metrics is None
    assert result.error.severity == Severity.FATAL
    assert "PETR4" in result.error.message


@pytest.mark.asyncio
async def test_search_partial_null_metrics_returns_partial_no_flag():
    with patch("app.services.yfinance.yf.Ticker") as MockTicker:
        MockTicker.side_effect = _ticker_side_effect(
            ticker_info=_fake_info(dividendYield=None),
            ticker_history=_fake_history(33.0, 30.0),
            ibov_history=_fake_history(102.0, 100.0)
        )

        svc = YfinanceService(ticker="PETR4")
        result = await svc.search()

    assert result.error is None
    assert result.metrics.dividend_yield is None
    assert result.metrics.pl == 15.2
    assert result.metrics.dev_ibov is not None


@pytest.mark.asyncio
async def test_search_stale_data_returns_fatal():
    stale_ts = int(time.time()) - (48 * 3600)
    with patch("app.services.yfinance.yf.Ticker") as MockTicker:
        MockTicker.return_value.info = _fake_info(regularMarketTime=stale_ts)

        svc = YfinanceService(ticker="PETR4", max_data_age_hours=24)
        result = await svc.search()

        assert result.metrics is None
        assert result.error.severity == Severity.FATAL
        assert "48.0h old" in result.error.message


@pytest.mark.asyncio
async def test_search_missing_market_time_skips_freshness_gate():
    info_no_mt = _fake_info()
    del info_no_mt["regularMarketTime"]
    with patch("app.services.yfinance.yf.Ticker") as MockTicker:
        MockTicker.side_effect = _ticker_side_effect(
            ticker_info=info_no_mt,
            ticker_history=_fake_history(33.0, 30.0),
            ibov_history=_fake_history(102.0, 100.0)
        )

        svc = YfinanceService(ticker="PETR4")
        result = await svc.search()

    assert result.error is None
    assert result.metrics is not None


@pytest.mark.asyncio
async def test_search_missing_ibov_history_returns_partial_devibov_none():
    with patch("app.services.yfinance.yf.Ticker") as MockTicker:
        MockTicker.side_effect = _ticker_side_effect(
            ticker_info=_fake_info(),
            ticker_history=_fake_history(33.0, 30.0),
            ibov_history=pd.DataFrame()  # empty IBOV history → dev_ibov None
        )

        svc = YfinanceService(ticker="PETR4")
        result = await svc.search()

    assert result.error is None
    assert result.metrics.dev_ibov is None
    assert result.metrics.pl == 15.2


@pytest.mark.asyncio
async def test_init_explicit_max_age_overrides_default():
    svc = YfinanceService(ticker="PETR4", max_data_age_hours=48)
    assert svc.max_data_age_hours == 48
    assert svc.market_index == "^BVSP"
