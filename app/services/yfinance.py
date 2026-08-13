from __future__ import annotations

from dataclasses import dataclass

from app.utils.flags import DataFlag


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
        raise NotImplementedError
