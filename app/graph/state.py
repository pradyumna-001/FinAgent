from datetime import datetime
from operator import add
from typing import Annotated, Literal, TypedDict

from app.utils.flags import DataFlag, Severity


class MacroOutput(TypedDict, total=False):
    """Macro-economic context fetched once per pipeline run (Selic, IPCA, FX)."""

    headline: str
    summary: str
    sources: list[str]
    fetched_at: str


class CompanyEvent(TypedDict, total=False):
    """Company-specific event for a single ticker (earnings, dividends, etc.)."""

    title: str
    date: str
    source: str
    summary: str


class QuantOutput(TypedDict, total=False):
    """Quantitative metrics for a single ticker (P/L, EV/EBITDA, P/VPA, DY, dev_ibov)."""

    pl: float | None
    ev_ebitda: float | None
    p_vpa: float | None
    dividend_yield: float | None
    dev_ibov: float | None
    fetched_at: str
    market_time: datetime | None


class RiskFlag(TypedDict, total=False):
    """Adversarial risk assessment for a single ticker."""

    probability: float
    impact: Literal["low", "medium", "high"]
    description: str
    severity: Severity


class RecommendationPayload(TypedDict, total=False):
    """Buy/sell/keep recommendation for a single ticker."""

    action: Literal["buy", "sell", "keep"]
    justification: str
    confidence: float
    created_at: str


def merge_dicts(left: dict, right: dict) -> dict:
    """Shallow-merge two dicts by key ({**left, **right}).

    Used as a LangGraph reducer for dict-keyed state fields so parallel
    fan-out slices can each contribute their own ticker key without
    overwriting other tickers' data.
    """
    return {**left, **right}


class AgentState(TypedDict):
    """LangGraph state for a multi-ticker morning-note pipeline run.

    Field groups:
    - Run identifiers: pipeline_run_id, morning_note_id, manager_id
    - Portfolio tickers: company_tickers, current_ticker (per-slice,
      injected by fan-out Send API; not merged)
    - Per-ticker data (merge_dicts reducer, keyed by ticker):
        macro_context (key = "global"), company_events, quant_metrics,
        risk_flags
    - Portfolio-level (from Consolidate node):
        portfolio_risk_flags, portfolio_data_flags, sector_weights
    - Editor output (consolidated):
        morning_note, recommendations, confidence_scores
    - Shared/reducer fields:
        data_freshness (per-ticker + "macro" + "portfolio"), flags
    - Persistence/output:
        recommendation_id (dict[str, int] | None, one entry per ticker's
        persisted Recommendation row), manager_decision, decision_channel
    """

    pipeline_run_id: str
    morning_note_id: str
    manager_id: int
    company_tickers: list[str]
    current_ticker: str

    macro_context: Annotated[dict[str, MacroOutput], merge_dicts]
    company_events: Annotated[dict[str, list[CompanyEvent]], merge_dicts]
    quant_metrics: Annotated[dict[str, QuantOutput | None], merge_dicts]
    risk_flags: Annotated[dict[str, list[RiskFlag]], merge_dicts]

    portfolio_risk_flags: list[RiskFlag]
    portfolio_data_flags: list[DataFlag]
    sector_weights: dict[str, float]

    morning_note: str | None
    recommendations: Annotated[dict[str, RecommendationPayload], merge_dicts]
    confidence_scores: Annotated[dict[str, dict[str, float]], merge_dicts]

    data_freshness: Annotated[dict[str, datetime], merge_dicts]
    flags: Annotated[list[DataFlag], add]

    recommendation_id: Annotated[dict[str, int], merge_dicts] | None
    manager_decision: str | None
    decision_channel: str | None


def create_initial_state_multi(
    *,
    manager_id: int,
    company_tickers: list[str],
    pipeline_run_id: str,
    morning_note_id: str,
) -> AgentState:
    """Create initial multi-ticker AgentState.

    All per-ticker dict fields start empty ({}) and are populated via
    merge_dicts as fan-out slices complete. recommendation_id is now
    dict[str, int] (one entry per ticker's persisted Recommendation row),
    not a single int.

    Args:
        manager_id: The manager owning the portfolio (RLS invariant).
        company_tickers: List of ticker symbols to process.
        pipeline_run_id: Unique id for this pipeline run.
        morning_note_id: Id of the MorningNote being generated.

    Returns:
        AgentState with all dict/reducer fields initialized to empty
        containers, ready for fan-out execution.
    """
    return {
        "manager_id": manager_id,
        "company_tickers": company_tickers,
        "current_ticker": "",
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
        "recommendation_id": {},
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
