from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, UTC

import yfinance as yf

from app.utils.flags import DataFlag, Severity


class YfinanceError(Exception):
    """Base for all YfinanceService failures. Callers can `except YfinanceError:` as catch-all."""


@dataclass(frozen=True)
class QuoteMetrics:
    pl: float | None
    ev_ebitda: float | None
    p_vpa: float | None
    dividend_yield: float | None
    dev_ibov: float | None
    fetched_at: str
    market_time: datetime | None


@dataclass(frozen=True)
class YfinanceResult:
    metrics: QuoteMetrics | None
    error: DataFlag | None


class YfinanceService:
    def __init__(self, ticker: str, market_index: str = "^BVSP", max_data_age_hours: int = 24) -> None:
        if not ticker:
            raise YfinanceError("ticker must be non-empty")
        self.ticker = ticker
        self.market_index = market_index
        self.max_data_age_hours = max_data_age_hours

    async def search(self) -> YfinanceResult:
        yf_ticker = f"{self.ticker}.SA"
        try:
            info = await asyncio.to_thread(lambda: yf.Ticker(yf_ticker).info)
        except Exception as exc:
            return YfinanceResult(
                metrics=None,
                error=DataFlag(
                    source="yfinance",
                    severity=Severity.WARNING,
                    message=f"Yfinance request error: {exc}"
                )
            )

        if not isinstance(info, dict):
            return YfinanceResult(
                metrics=None,
                error=DataFlag(
                    source="yfinance",
                    severity=Severity.WARNING,
                    message="Yfinance returned no info dict"
                )
            )

        market_time_raw = info.get("regularMarketTime")
        market_time_dt: datetime | None = None
        if market_time_raw is not None:
            try:
                market_time_dt = datetime.fromtimestamp(float(market_time_raw), UTC)
            except (TypeError, ValueError):
                market_time_dt = None
                
        if market_time_dt is not None:
            data_age_hours = (datetime.now(UTC).timestamp() - market_time_dt.timestamp()) / 3600
            if data_age_hours > self.max_data_age_hours:
                return YfinanceResult(
                    metrics=None,
                    error=DataFlag(
                        source="yfinance",
                        severity=Severity.FATAL,
                        message=(
                            f"Yfinance data for {self.ticker!r} is "
                            f"{data_age_hours:.1f}h old (max {self.max_data_age_hours}h)"
                        )
                    )
                )

        expected_keys = {"trailingPE", "enterpriseToEbitda", "priceToBook", "dividendYield"}
        present_keys = {k for k, v in info.items() if v is not None} & expected_keys
        if not present_keys:
            return YfinanceResult(
                metrics=None,
                error=DataFlag(
                    source="yfinance",
                    severity=Severity.FATAL,
                    message=(
                        f"Yfinance returned no expected metrics for {self.ticker!r}"
                        f" - schema may have changed"
                    )
                )
            )

        try:
            ibov_history = await asyncio.to_thread(
                lambda: yf.Ticker(self.market_index).history(period="2d")
            )
            ticker_history = await asyncio.to_thread(lambda: yf.Ticker(yf_ticker).history(period="2d"))
        except Exception as exc:
            return YfinanceResult(
                metrics=None,
                error=DataFlag(
                    source="yfinance",
                    severity=Severity.WARNING,
                    message=f"Yfinance IBOV history error: {exc}"
                )
            )

        def _one_day_return(df) -> float | None:
            if df is None or df.empty or len(df) < 2:
                return None
            closes = df["Close"].tolist()
            if closes[-2] == 0:
                return None
            return (closes[-1] - closes[-2]) / closes[-2]

        ticker_return = _one_day_return(ticker_history)
        ibov_return = _one_day_return(ibov_history)
        dev_ibov = None
        if ticker_return is not None and ibov_return is not None:
            dev_ibov = ticker_return - ibov_return

        metrics = QuoteMetrics(
            pl=info.get("trailingPE"),
            ev_ebitda=info.get("enterpriseToEbitda"),
            p_vpa=info.get("priceToBook"),
            dividend_yield=info.get("dividendYield"),
            dev_ibov=dev_ibov,
            fetched_at=datetime.now(UTC).isoformat(),
            market_time=market_time_dt,
        )

        return YfinanceResult(metrics=metrics, error=None)
