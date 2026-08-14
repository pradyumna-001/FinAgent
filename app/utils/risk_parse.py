import json
import logging
import re
from typing import get_args

from app.graph.state import RiskFlag
from app.utils.flags import Severity


logger = logging.getLogger(__name__)

_VALID_IMPACTS = set(get_args(RiskFlag.__annotations__["impact"]))
_VALID_SEVERITIES = {s.value for s in Severity}


def parse_risk_json(text: str | None) -> tuple[list[RiskFlag], int]:
    """Parse raw LLM text into a validated list of RiskFlag dicts.
    Tolerant: drops individual invalid items and keeps the rest.
    Returns (flags, dropped_count). dropped_count is the number of
    items that failed validation and were skipped.
    Never raises.
    """
    if not text:
        return [], 0

    match = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if match is None:
        return [], 0
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return [], 0
    if not isinstance(parsed, list):
        return [], 0

    flags: list[RiskFlag] = []
    dropped = 0
    for item in parsed:
        if not isinstance(item, dict):
            dropped += 1
            continue
        prob = item.get("probability")
        impact = item.get("impact")
        desc = item.get("description")
        sev = item.get("severity")

        if not isinstance(prob, (int, float)) or not 0.0 <= prob <= 1.0:
            dropped += 1
            logger.warning(
                "risk_parse_drop",
                extra={"reason": "invalid_probability", "value": prob},
            )
            continue
        if impact not in _VALID_IMPACTS:
            dropped += 1
            logger.warning(
                "risk_parse_drop",
                extra={"reason": "invalid_impact", "value": impact},
            )
            continue
        if not isinstance(desc, str) or not desc:
            dropped += 1
            logger.warning(
                "risk_parse_drop",
                extra={"reason": "invalid_description", "value": desc},
            )
            continue
        if sev not in _VALID_SEVERITIES:
            dropped += 1
            logger.warning(
                "risk_parse_drop",
                extra={"reason": "invalid_severity", "value": sev},
            )
            continue

        flags.append(
            RiskFlag(
                probability=float(prob),
                impact=impact,
                description=desc,
                severity=sev,
            )
        )
    return flags, dropped
