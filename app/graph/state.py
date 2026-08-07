from datetime import datetime
from typing import TypedDict, Literal

from app.utils.flags import DataFlag, Severity


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


class AgentState(TypedDict):
    pipeline_run_id: str
    morning_note_id: str
    manager_id: int
    company_ticker: str
    macro_context: MacroOutput | None
    company_events: list[CompanyEvent]
    quant_metrics: QuantOutput | None
    risk_flags: list[RiskFlag]
    morning_note: str | None
    recommendation: RecommendationPayload | None
    confidence_scores: dict[str, float]
    data_freshness: dict[str, datetime]
    flags: list[DataFlag]


def create_initial_state(
        *,
        manager_id: int,
        company_ticker: str,
        pipeline_run_id: str,
        morning_note_id: str
) -> AgentState:
    return {
        "manager_id": manager_id,
        "company_ticker": company_ticker,
        "pipeline_run_id": pipeline_run_id,
        "morning_note_id": morning_note_id,
        "macro_context": None,
        "company_events": [],
        "quant_metrics": None,
        "risk_flags": [],
        "morning_note": None,
        "recommendation": None,
        "confidence_scores": {},
        "data_freshness": {},
        "flags": [],
    }
