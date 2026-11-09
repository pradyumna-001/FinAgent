from app.utils.flags import DataFlag

SECTION_SOURCE_MAP: dict[str, list[str]] = {
    "macro": ["tavily"],
    "company": ["tavily"],
    "quant": ["yfinance"],
    "risk": ["risk_parse"],
}


def apply_confidence_penalties(
    confidence_scores: dict[str, dict[str, float]],
    data_flags: list[DataFlag]
) -> tuple[dict[str, dict[str, float]], list[str]]:
    """Apply DataFlag penalties to confidence scores per ticker.

    Returns: (updated_confidence_scores, warning_messages_for_embedding)
    """
    updated_scores: dict[str, dict[str, float]] = {}
    warnings: list[str] = []

    for ticker, scores in confidence_scores.items():
        ticker_updated = scores.copy()
        for section, sources in SECTION_SOURCE_MAP.items():
            flagged = any(flag.source in sources for flag in data_flags)
            if flagged:
                original = ticker_updated.get(section, 1.0)
                ticker_updated[section] = min(original, 0.49)
                warnings.append(f"[Aviso]: {ticker} - {section} - dados incompletos ou falhos")

        section_scores = [ticker_updated.get(s, 1.0) for s in ("macro", "company", "quant", "risk")]
        ticker_updated["overall"] = sum(section_scores) / len(section_scores) if section_scores else 0.0
        updated_scores[ticker] = ticker_updated

    return updated_scores, warnings
