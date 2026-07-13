from datetime import datetime
from typing import TypedDict, Any
from pydantic import BaseModel, Field

# 1. granular sub-schemas (the data payloads)

class MacroOutput(BaseModel):
    """Structured data returned by the MacroAgent."""
    summary: str = Field(..., description="Summary of the current macroeconomic scenario.")
    selic_rate: str = Field(..., description="Current or projected Selic interest rate.")
    inflation_ipca: str = Field(..., description="Inflation metrics (IPCA index tracking).")
    fx_rate: str = Field(..., description="Foreign exchange scenario context (USD/BRL).")


class CompanyEvent(BaseModel):
    """A single relevant event or news item discovered by the CompanyAgent."""
    headline: str = Field(..., description="Title of the corporate news or event.")
    source: str = Field(..., description="Information source (e.g., CVM, Valor Econômico).")
    impact_assessment: str = Field(..., description="Initial assessment of impact on the thesis.")


class QuantOutput(BaseModel):
    """Quantitative metrics extracted and validated by the QuantAgent."""
    pe_ratio: float | None = Field(None, description="Price to Earnings ratio (P/L).")
    ev_ebitda: float | None = Field(None, description="Enterprise Value to EBITDA.")
    dividend_yield: float | None = Field(None, description="Current updated Dividend Yield percentage.")
    is_calculated: bool = Field(False, description="Flag indicating if metrics were successfully calculated.")


class RiskFlag(BaseModel):
    """A counter-argument or critical risk identified by the RiskAgent."""
    title: str = Field(..., description="Short name of the risk (e.g., Tail Risk, High Leverage).")
    description: str = Field(..., description="Detailed explanation of why this threatens the thesis.")
    probability: str = Field(..., description="Estimated probability (Low | Medium | High).")
    impact: str = Field(..., description="Estimated financial impact (Low | Medium | High).")


class RecommendationOutput(BaseModel):
    """The formal investment recommendation built by the EditorAgent."""
    action: str = Field(..., description="Recommended action (BUY | SELL | NEUTRAL).")
    justification: str = Field(..., description="Detailed text justifying the choice of action.")


class DataFlag(BaseModel):
    """A visibility tracking tool for broken data streams (Fail Visible Principle)."""
    source: str = Field(..., description="The API or broker stream that failed (e.g., b3_api, tavily).")
    reason: str = Field(..., description="The cause of failure (e.g., data_outdated, rate_limit).")
    message: str = Field(..., description="Human-readable message explaining the error to the manager.")

# 2. main agent state (the central scratchpad)

def append_item(current: list, new_items: list) -> list:
    return current + new_items

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
    recommendation: RecommendationOutput | None

    confidence_scores: dict[str, float]
    data_freshness: dict[str, datetime]

    flags: Annotated[list[DataFlag], append_item]
    