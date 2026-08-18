from datetime import datetime, UTC

import json
import logging

from app.graph.state import AgentState
from app.prompts.editor import EDITOR_PROMPTS
from app.services.llm import summarize_nemotron
from app.utils.editor_confidence import apply_confidence_penalties
from app.utils.flags import DataFlag, Severity


logger = logging.getLogger(__name__)


async def editor_agent_node(state: AgentState) -> dict:
    logger.info(
        "editor_agent_start",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "morning_note_id": state["morning_note_id"],
            "manager_id": state["manager_id"],
            "flags": state["flags"]
        }
    )

    new_flags = []

    raw_flags = state.get("flags", [])
    data_flags = []
    for f in raw_flags:
        if isinstance(f, DataFlag):
            data_flags.append(f)
        elif isinstance(f, dict) and "source" in f:
            sev = f["severity"]
            if isinstance(sev, Severity):
                severity = sev
            else:
                severity = Severity(sev)
            data_flags.append(DataFlag(
                source=f["source"],
                severity=severity,
                message=f["message"],
            ))
        else:
            logger.warning("invalid_flag_in_state", extra={"flag": f})

    user_prompt = EDITOR_PROMPTS.build_user_prompt(
        macro_context=state.get("macro_context"),
        company_events=state.get("company_events", []),
        quant_metrics=state.get("quant_metrics"),
        risk_flags=state.get("risk_flags", []),
        data_flags=data_flags
    )

    raw_text = await summarize_nemotron(
        system=EDITOR_PROMPTS.system,
        user=user_prompt
    )

    if raw_text is None:
        new_flags.append(
            DataFlag(
                source="summarize_nemotron",
                severity=Severity.FATAL,
                message="Summarization failed"
            )
        )
        return {
            "morning_note": None,
            "recommendation": None,
            "confidence_scores": {},
            "data_freshness": {"editor": datetime.now(UTC)},
            "flags": new_flags
        }

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        new_flags.append(
            DataFlag(
                source="editor_parse",
                severity=Severity.WARNING,
                message="Failed to parse EditorAgent JSON response"
            )
        )
        return {
            "morning_note": None,
            "recommendation": None,
            "confidence_scores": {},
            "data_freshness": {"editor": datetime.now(UTC)},
            "flags": new_flags
        }

    if parsed.get("morning_note") is not None and parsed.get("recommendation") is not None and parsed.get("confidence_scores") is not None:
        is_morning_note = isinstance(parsed["morning_note"], str)
        is_recommendation = (
            isinstance(parsed["recommendation"], dict) and 
            set(parsed["recommendation"].keys()) == {"action", "justification", "confidence"} and 
            parsed["recommendation"]["action"] in ("buy", "sell", "keep") and 
            isinstance(parsed["recommendation"]["justification"], str) and 
            isinstance(parsed["recommendation"]["confidence"], float)
        )
        is_confidence_scores = (
            isinstance(parsed["confidence_scores"], dict) and 
            all(isinstance(v, float) for v in parsed["confidence_scores"].values()) and 
            set(parsed["confidence_scores"].keys()) == {"macro", "company", "quant", "risk", "overall"} 
        )

        if (
            not is_morning_note or 
            not is_recommendation or 
            not is_confidence_scores
        ):
            new_flags.append(
                DataFlag(
                    source="editor_parse",
                    severity=Severity.WARNING,
                    message="Failed to parse EditorAgent JSON response"
                )
            )
            return {
                "morning_note": None,
                "recommendation": None,
                "confidence_scores": {},
                "data_freshness": {"editor": datetime.now(UTC)},
                "flags": new_flags
            }
    else:
        new_flags.append(
            DataFlag(
                source="editor_parse",
                severity=Severity.WARNING,
                message="Missing keys"
            )
        )
        return {
            "morning_note": None,
            "recommendation": None,
            "confidence_scores": {},
            "data_freshness": {"editor": datetime.now(UTC)},
            "flags": new_flags
        }

    penalized_scores, warnings = apply_confidence_penalties(parsed["confidence_scores"], state["flags"])
    morning_note = parsed["morning_note"]
    if warnings:
        morning_note = "\n\n".join(warnings) + "\n\n" + morning_note

    return {
        "morning_note": morning_note,
        "recommendation": parsed["recommendation"],
        "confidence_scores": penalized_scores,
        "data_freshness": {"editor": datetime.now(UTC)},
        "flags": new_flags
    }
