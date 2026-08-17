import json

from app.utils.risk_parse import parse_risk_json

def test_parse_risk_valid_single_risk() -> None:
    text = '[{"probability": 0.3, "impact": "low", "description": "Limited downside risk", "severity": "info"}]'
    flags, dropped = parse_risk_json(text)
    assert dropped == 0
    assert len(flags) == 1
    assert flags[0]["probability"] == 0.3
    assert flags[0]["impact"] == "low"
    assert flags[0]["description"] == "Limited downside risk"
    

def test_parse_risk_three_risks() -> None:
    text = (
        '['
        '{"probability": 0.3, "impact": "low", "description": "risk one", "severity": "info"},'
        '{"probability": 0.6, "impact": "medium", "description": "risk two", "severity": "warning"},'
        '{"probability": 0.9, "impact": "high", "description": "risk three", "severity": "fatal"}'
        ']'
    )
    flags, dropped = parse_risk_json(text)
    assert dropped == 0
    assert len(flags) == 3
    assert [f["severity"] for f in flags] == ["info", "warning", "fatal"]


def test_parse_risk_wrapped_in_prose() -> None:
    text = (
        'Here is the analysis:\n'
        '[{"probability": 0.5, "impact": "medium", "description": "macro risk", "severity": "warning"}]\n'
        'Done.'
    )
    flags, dropped = parse_risk_json(text)
    assert dropped == 0
    assert len(flags) == 1
    assert flags[0]["description"] == "macro risk"


def test_parse_risk_malformed_json() -> None:
    text = '[{"probability": 0.3, "impact": "low", "description": "broken"'
    flags, dropped = parse_risk_json(text)
    assert flags == []
    assert dropped == 0


def test_parse_risk_bad_probability_dropped() -> None:
    text = (
        '['
        '{"probability": 1.5, "impact": "low", "description": "bad prob", "severity": "info"},'
        '{"probability": 0.4, "impact": "low", "description": "good one", "severity": "info"}'
        ']'
    )
    flags, dropped = parse_risk_json(text)
    assert dropped == 1
    assert len(flags) == 1
    assert flags[0]["description"] == "good one"


def test_parse_risk_bad_impact_dropped() -> None:
    text = (
        '['
        '{"probability": 0.5, "impact": "extreme", "description": "bad impact", "severity": "info"},'
        '{"probability": 0.5, "impact": "high", "description": "good one", "severity": "info"}'
        ']'
    )
    flags, dropped = parse_risk_json(text)
    assert dropped == 1
    assert len(flags) == 1
    assert flags[0]["description"] == "good one"


def test_parse_risk_bad_severity_dropped() -> None:
    text = (
        '['
        '{"probability": 0.5, "impact": "low", "description": "bad sev", "severity": "critical"},'
        '{"probability": 0.5, "impact": "low", "description": "good one", "severity": "info"}'
        ']'
    )
    flags, dropped = parse_risk_json(text)
    assert dropped == 1
    assert len(flags) == 1
    assert flags[0]["description"] == "good one"


def test_parse_risk_empty_input() -> None:
    flags, dropped = parse_risk_json("")
    assert flags == []
    assert dropped == 0


def test_parse_risk_none_input() -> None:
    flags, dropped = parse_risk_json(None)
    assert flags == []
    assert dropped == 0