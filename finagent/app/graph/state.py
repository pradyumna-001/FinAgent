from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, TypedDict
from pydantic import BaseModel, Field
from app.utils.data_preprocessing import DataFlag

# 1. Helper Output Models (Schemas)

class MacroOutput(BaseModel):
    """Structured macroeconomic indicators and contextual insights"""
    gdp_growth: Optional[float] = Field(None, description="GDP Growth rate percentage")
    inflation_rate: Optional[float] = Field(None, description="Inflation rate percentage")
    interest_rate: Optional[float] = Field(None, description="Central bank policy interest rate percentage")
    analysis_summary: str = Field(..., description="Synthesis of current macroeconomic impacts")

class CompanyEvent(BaseModel):
    """Represents a key corporate development event or date"""
    event_name: str = Field(..., description="The type/name of corporate event (e.g., Earnings, M&A)")
    event_date: datetime = Field(..., description="Date of the event")
    significance: str = Field("medium", description="Significance level: low, medium, high")
    description: str = Field(..., description="Brief summary of the event or expectations")

class QuantOutput(BaseModel):
    """Standardized quantitative and financial metrics"""
    pe_ratio: Optional[float] = Field(None, description="Price to Earnings Ratio")
    ev_ebitda: Optional[float] = Field(None, description="Enterprise Value to EBITDA")
    dividend_yield: Optional[float] = Field(None, description="Dividend Yield percentage")
    momentum_signal: str = Field("neutral", description="Quantitative momentum signal: bullish, bearish, neutral")
    interpretation: Optional[str] = Field(None, description="Qualitativecommentary interpreting the calculated metrics")

class RiskFlag(BaseModel):
    """Specific risk metric classification with severity scale"""
    risk_type: str = Field(..., description="Type of risk (e.g., Market, Regulatory, Liquidity)")
    severity: str = Field("low", description="Severity level: low, medium, high")
    description: str = Field(..., description="Description of the risk factor identified")

class Recommendation(BaseModel):
    """Final output investment allocation thesis"""
    action: str = Field(..., description="Target action: BUY, HOLD, SELL, UNDERWEIGHT")
    target_weight: float = Field(..., description="Recommended portfolio weight percentage")
    horizon_months: int = Field(12, description="Investment horizon in months")
    thesis_summary: str = Field(..., description="Core bullet points supporting this recommendation")

# 2. Main AgentState TypedDict

class AgentState(TypedDict):
    """Main state carried throughout the LangGraph milti-agent execution pipeline"""
    pipeline_run_id: str
    morning_note_id: str
    manager_id: int
    company_ticker: str

    macro_context: Optional[MacroOutput]
    company_events: List[CompanyEvent]
    quant_metrics: Optional[QuantOutput]
    risk_flags: List[RiskFlag]

    morning_note: Optional[str]
    recommendation: Optional[Recommendation]

    confidence_scores: Dict[str, float]
    data_freshness: Dict[str, datetime]
    flags: List[DataFlag]

# 3. State Operations & Invariants

def create_initial_state(
        pipeline_run_id: str,
        morning_note_id: str,
        manager_id: int,
        company_ticker: str
) -> AgentState:
    """Generates a default initial AgentState with guaranteed empty structures initialized"""
    if not manager_id or not isinstance(manager_id, int):
        raise ValueError("manager_id must be a valid, non-zero integer")
    
    return {
        "pipeline_run_id": pipeline_run_id,
        "morning_note_id": morning_note_id,
        "manager_id": manager_id,
        "company_ticker": company_ticker,
        "macro_context": None,
        "company_events": [],
        "quant_metrics": None,
        "risk_flags": [],
        "morning_note": None,
        "recommendation": None,
        "confidence_scores": {},
        "data_freshness": {},
        "flags": []
    }

def validate_state(state: AgentState) -> None:
    """Asserts structural invariants on the state to prevent downstream agent processing corruption"""
    if "manager_id" not in state or state["manager_id"] is None:
        raise ValueError("State Invariant Violation: 'manager_id' is missing or null")

    if not isinstance(state["manager_id"], int) or state["manager_id"] <= 0:
        raise ValueError(f"State Invariant Violation: 'manager_id' must be a positive integer. Got {state.get('manager_id')}")
    
    if not state.get("pipeline_run_id"):
        raise ValueError("State Invariant Violation: 'pipeline_run_id' cannot be empty")
    
    if not state.get("company_ticker"):
        raise ValueError("State Invariant Violation: 'company_ticker' cannot be empty")
    
    list_fields = ["company_events", "risk_flags", "flags"]
    for field in list_fields:
        if not isinstance(state.get(field), list):
            raise TypeError(f"State Invariant Violation: Field '{field}' must be a list structure")
        
    dict_fields = ["confidence_scores", "data_freshness"]
    for field in dict_fields:
        if not isinstance(state.get(field), dict):
            raise TypeError(f"State Invariant Violation: Field '{field}' must be a dictionary structure")
