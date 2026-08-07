import pytest

from app.graph.state import create_initial_state, validate_state, InvalidStateError
from app.utils.flags import Severity


def test_validate_state_rejects_missing_manager_id() -> None:
    state = {
        "company_ticker": "PETR4",
        "pipeline_run_id": "pipeline_run_id",
        "morning_note_id": "morning_note_id",
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
    with pytest.raises(InvalidStateError, match="manager_id"):
        validate_state(state)


def test_validate_state_rejects_invalid_manager_id() -> None:
    state = {
        "manager_id": -10,
        "company_ticker": "PETR4",
        "pipeline_run_id": "pipeline_run_id",
        "morning_note_id": "morning_note_id",
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
    with pytest.raises(InvalidStateError, match="manager_id"):
        validate_state(state)


def test_validate_state_rejects_invalid_severity() -> None:
    state = {
        "manager_id": 1,
        "company_ticker": "PETR4",
        "pipeline_run_id": "pipeline_run_id",
        "morning_note_id": "morning_note_id",
        "macro_context": None,
        "company_events": [],
        "quant_metrics": None,
        "risk_flags": [
            {
                "probability": 0.1,
                "impact": "low",
                "description": "Inflação acima do esperado aumenta risco de alta adicional da Selic.",
                "severity": "a"
            }
        ],
        "morning_note": None,
        "recommendation": None,
        "confidence_scores": {},
        "data_freshness": {},
        "flags": [],
    }
    with pytest.raises(InvalidStateError, match="severity"):
        validate_state(state)
    

def test_validate_state_rejects_invalid_probability() -> None:
    state = {
        "manager_id": 1,
        "company_ticker": "PETR4",
        "pipeline_run_id": "pipeline_run_id",
        "morning_note_id": "morning_note_id",
        "macro_context": None,
        "company_events": [],
        "quant_metrics": None,
        "risk_flags": [
            {
                "probability": 10,
                "impact": "low",
                "description": "Inflação acima do esperado aumenta risco de alta adicional da Selic.",
                "severity": Severity.WARNING
            }
        ],
        "morning_note": None,
        "recommendation": None,
        "confidence_scores": {},
        "data_freshness": {},
        "flags": [],
    }
    with pytest.raises(InvalidStateError, match="probability"):
        validate_state(state)


def test_validate_state_accepts_valid_state() -> None:
    state = create_initial_state(
        manager_id=1, 
        company_ticker="PETR4", 
        pipeline_run_id="run-123", 
        morning_note_id="note-123"
    )
    validate_state(state)
    