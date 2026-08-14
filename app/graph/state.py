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

        for flag in state.get("risk_flags", []):
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