from app.utils.flags import DataFlag, Severity


SECTION_SOURCE_MAP: dict[str, list[str]] = {
    "macro": ["tavily"],
    "company": ["tavily"],
    "quant": ["yfinance"],
    "risk": ["risk_parse"],
}


def apply_confidence_penalties(
    confidence_scores: dict[str, float],
    data_flags: list[DataFlag]
) -> tuple[dict[str, float], list[str]]:
    """Apply DataFlag penalties to confidence scores.

    Returns: (updated_confidence_scores, warning_messages_for_embedding)
    """
    updated_scores = confidence_scores.copy()
    warnings: list[str] = []
    
    for section, sources in SECTION_SOURCE_MAP.items():
        flagged = any(flag.source in sources for flag in data_flags)
        if flagged:
            original = confidence_scores.get(section, 1.0)
            updated_scores[section] = min(original, 0.49)
            warnings.append(f"[Aviso]: {section} - dados incompletos ou falhos")

    section_scores = [updated_scores.get(s, 1.0) for s in ("macro", "company", "quant", "risk")]
    updated_scores["overall"] = sum(section_scores) / len(section_scores) if section_scores else 0.0
    return updated_scores, warnings
    