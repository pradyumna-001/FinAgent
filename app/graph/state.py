from datetime import datetime
from operator import add
from typing import Annotated, Literal, TypedDict

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
    pl: float | None
    ev_ebitda: float | None
    p_vpa: float | None
    dividend_yield: float | None
    dev_ibov: float | None
    fetched_at: str
    market_time: datetime | None


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


def merge_dicts(left: dict, right: dict) -> dict:
    return {**left, **right}


class AgentState(TypedDict):
    pipeline_run_id: str
    morning_note_id: str
    manager_id: int
    company_tickers: list[str]

    # Per-ticker data — merge_dicts reducer (shallow merge by key)
    macro_context: Annotated[dict[str, MacroOutput], merge_dicts]               # key = "global"
    company_events: Annotated[dict[str, list[CompanyEvent]], merge_dicts]       # {"PETR4": [...], "VALE3": [...]}
    quant_metrics: Annotated[dict[str, QuantOutput | None], merge_dicts]        # {"PETR4": {...}, "VALE3": None}
    risk_flags: Annotated[dict[str, list[RiskFlag]], merge_dicts]               # {"PETR4": [...], "VALE3": [...]}

    # Portfolio-level (from Consolidate node)
    portfolio_risk_flags: list[RiskFlag]
    portfolio_data_flags: list[DataFlag]
    sector_weights: dict[str, float]

    # Editor output (consolidated)
    morning_note: str | None
    recommendations: Annotated[dict[str, RecommendationPayload], merge_dicts]   # {"PETR4": {...}, "VALE3": {...}}
    confidence_scores: Annotated[dict[str, dict[str, float]], merge_dicts]      # {"PETR4": {"macro": 0.9, ...}, ...}

    # Shared/reducer fields
    data_freshness: Annotated[dict[str, datetime], merge_dicts]  # per-ticker + "macro" + "portfolio"
    flags: Annotated[list[DataFlag], add]

    # Persistence/output
    recommendation_id: int | None
    manager_decision: str | None
    decision_channel: str | None


def create_initial_state_multi(
    *,
    manager_id: int,
    company_tickers: list[str],
    pipeline_run_id: str,
    morning_note_id: str,
) -> AgentState:
    """NEW: Multi-ticker initial state."""
    return {
        "manager_id": manager_id,
        "company_tickers": company_tickers,
        "pipeline_run_id": pipeline_run_id,
        "morning_note_id": morning_note_id,
        "macro_context": {},
        "company_events": {},
        "quant_metrics": {},
        "risk_flags": {},
        "portfolio_risk_flags": [],
        "portfolio_data_flags": [],
        "sector_weights": {},
        "morning_note": None,
        "recommendations": {},
        "confidence_scores": {},
        "data_freshness": {},
        "flags": [],
        "recommendation_id": None,
        "manager_decision": None,
        "decision_channel": None,
    }


def create_initial_state(
    *,
    manager_id: int,
    company_ticker: str,
    company_tickers: list[str] | None = None,
    pipeline_run_id: str,
    morning_note_id: str,
) -> AgentState:
    """Backward-compatible wrapper. Use create_initial_state_multi for new code."""
    if company_tickers is not None:
        tickers = company_tickers
    else:
        tickers = [company_ticker]
        import warnings
        warnings.warn(
            "create_initial_state(company_ticker=...) is deprecated; "
            "use create_initial_state_multi(company_tickers=[...])",
            DeprecationWarning,
            stacklevel=2,
        )

    return create_initial_state_multi(
        manager_id=manager_id,
        company_tickers=tickers,
        pipeline_run_id=pipeline_run_id,
        morning_note_id=morning_note_id,
    )


class InvalidStateError(ValueError):
    """Raised when an AgentState fails invariant validation."""

    def validate(self, state: AgentState) -> None:
        """Validate AgentState invariants. Raises InvalidStateError on violation.

        Invariants:
        - state["manager_id"] is a positive int (RLS invariant)
        - RiskFlag.severity values are valid Severity members (if risk_flags present)
        - RiskFlag.probability values are in [0.0, 1.0] (if risk_flags present)
        """
        manager_id = state.get("manager_id")

        if manager_id is None:
            raise InvalidStateError(
                f"AgentState missing required field 'manager_id', got {manager_id}."
            )
        if not (isinstance(manager_id, int) and manager_id > 0):
            raise InvalidStateError(
                f"AgentState.manager_id must be a positive int, got {manager_id}."
            )

        # Check risk_flags dict structure
        for ticker, flags in state.get("risk_flags", {}).items():
            for flag in flags:
                severity = flag.get("severity")
                prob = flag.get("probability")

                if severity is not None and severity not in Severity.__members__.values():
                    raise InvalidStateError(
                        f"RiskFlag.severity must be a valid Severity, got {severity!r}."
                    )
                if prob is not None and not 0.0 <= prob <= 1.0:
                    raise InvalidStateError(
                        f"RiskFlag.probability must be in [0.0, 1.0], got {prob}."
                    )
