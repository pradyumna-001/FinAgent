from app.utils.editor_confidence import apply_confidence_penalties
from app.utils.flags import DataFlag, Severity


_SCORES = {
        "macro": 0.8,
        "company": 0.7,
        "quant": 0.9,
        "risk": 0.6
    }


def test_apply_confidence_no_flags() -> None:
    result, warnings = apply_confidence_penalties(_SCORES, [])

    assert all(_SCORES[score] == result[score] for score in _SCORES)
    assert result["overall"] == 0.75
    assert warnings == []
    

def test_apply_confidence_tavily_flag_penalizes_macro_and_company() -> None:
    flags = [
        DataFlag(
            source="tavily",
            severity=Severity.WARNING,
            message="Tavily 500"
        )
    ]
    result, warnings = apply_confidence_penalties(_SCORES, flags)

    assert result["macro"] == 0.49
    assert result["company"] == 0.49
    assert result["quant"] == _SCORES["quant"]
    assert result["risk"] == _SCORES["risk"]
    assert len(warnings) == 2
    assert any("macro" in w for w in warnings)
    assert any("company" in w for w in warnings)


def test_apply_confidence_yfinance_flag_penalizes_quant() -> None:
    flags = [
        DataFlag(
            source="yfinance",
            severity=Severity.FATAL,
            message="yfinance timeout"
        )
    ]
    result, warnings = apply_confidence_penalties(_SCORES, flags)

    assert result["macro"] == _SCORES["macro"]
    assert result["company"] == _SCORES["company"]
    assert result["quant"] == 0.49
    assert result["risk"] == _SCORES["risk"]
    assert len(warnings) == 1
    assert any("quant" in w for w in warnings)


def test_apply_confidence_risk_parse_flag_penalizes_risk() -> None:
    flags = [
        DataFlag(
            source="risk_parse",
            severity=Severity.WARNING,
            message="parse dropped"
        )
    ]
    result, warnings = apply_confidence_penalties(_SCORES, flags)

    assert result["macro"] == _SCORES["macro"]
    assert result["company"] == _SCORES["company"]
    assert result["quant"] == _SCORES["quant"]
    assert result["risk"] == 0.49
    assert len(warnings) == 1
    assert any("risk" in w for w in warnings)


def test_apply_confidence_multiple_flags_same_section() -> None:
    flags = [
        DataFlag(
            source="tavily",
            severity=Severity.WARNING,
            message="tavily 500"
        ),
        DataFlag(
            source="tavily",
            severity=Severity.WARNING,
            message="tavily 404"
        )
    ]
    result, warnings = apply_confidence_penalties(_SCORES, flags)

    assert result["macro"] == 0.49
    assert result["company"] == 0.49
    assert result["quant"] == _SCORES["quant"]
    assert result["risk"] == _SCORES["risk"]
    assert len(warnings) == 2
    assert any("macro" in w for w in warnings)
    assert any("company" in w for w in warnings)


def test_apply_confidence_partial_scores_defaults_to_one() -> None:
    scores = {
        "macro": 0.5,
        "company": 0.5
    }
    result, _ = apply_confidence_penalties(scores, [])

    assert result.get("quant", 1.0) == 1.0
    assert result.get("risk", 1.0) == 1.0
    assert result["overall"] == (sum(scores.values()) + result.get("quant", 1.0) + result.get("risk", 1.0)) / 4


def test_apply_confidence_low_original_not_penalized_further() -> None:
    scores = {
        "macro": 0.3,
        "company": 0.7,
        "quant": 0.9,
        "risk": 0.6
    }
    flags = [
        DataFlag(
            source="tavily",
            severity=Severity.WARNING,
            message="Tavily 500"
        )
    ]
    result, warnings = apply_confidence_penalties(scores, flags)

    assert result["macro"] == 0.3
    assert result["company"] == 0.49
    assert len(warnings) == 2
    assert any("macro" in w for w in warnings)
    assert any("company" in w for w in warnings)
