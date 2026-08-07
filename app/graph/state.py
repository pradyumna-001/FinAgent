from typing import TypedDict, Literal

from app.utils.flags import Severity


class MacroOutput(TypedDict, total=False):
    headline: str
    summary: str
    sources: list[str]
    fetched_at: str


class CompanyEvent(TypedDict, total=False):
    title: str
    date: str
    source: str
    summary: str


class QuantOutput(TypedDict, total=False):
    pl: float
    ev_ebitda: float
    p_vpa: float
    dividend_yield: float
    dev_ibov: float
    fetched_at: str


class RiskFlag(TypedDict, total=False):
    probability: float
    impact: Literal["low", "medium", "high"]
    description: str
    severity: Severity


class RecommendationPayload(TypedDict, total=False):
    action: Literal["buy", "sell", "keep"]
    justification: str
    confidence: float
    created_at: str
