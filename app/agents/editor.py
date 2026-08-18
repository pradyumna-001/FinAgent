from datetime import datetime, UTC

import json
import logging

from app.graph.state import AgentState
from app.prompts.editor import EDITOR_PROMPTS
from app.services.llm import summarize_nemotron
from app.utils.flags import DataFlag, Severity



logger = logging.getLogger(__name__)


async def editor_agent_node(state: AgentState) -> AgentState:
    # TODO: logger
    logger.info(
        "editor_agent_start",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "morning_note_id": state["morning_note_id"],
            "manager_id": state["manager_id"]
        }
    )
    # macro_context: MacroOutput | None,
    # company_events: list[CompanyEvent],
    # quant_metrics: QuantOutput | None,
    # risk_flags: list[RiskFlag],
    # data_flags: list[DataFlag]
    # TODO: connect with service
    user_prompt = EDITOR_PROMPTS.build_user_prompt(
        macro_context=state.get("macro_context"),
        company_events=state.get("company_events", []),
        quant_metrics=state.get("quant_metrics"),
        risk_flags=state.get("risk_flags", []),
        data_flags=state.get("flags", []),
    )

    raw_text = await summarize_nemotron(
        system=EDITOR_PROMPTS.system,
        user=user_prompt
    )

    # TODO: check for errors returned by the service and deal
    if raw_text is None:
        state["flags"].append(
            DataFlag(
                source="summarize_nemotron",
                severity=Severity.FATAL,
                message="Summarization failed"
            )
        )
        state["morning_note"] = None
        state["recommendation"] = None
        state["confidence_scores"] = {}
        state["data_freshness"]["editor"] = datetime.now(UTC)
        return state


    # TODO: prepare th output
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        state["flags"].append(
            DataFlag(
                source="editor_parse",
                severity=Severity.WARNING,
                message="Failed to parse EditorAgent JSON response"
            )
        )
        state["morning_note"] = None
        state["recommendation"] = None
        state["confidence_scores"] = {}
        state["data_freshness"]["editor"] = datetime.now(UTC)
        return state

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
            state["flags"].append(
                DataFlag(
                    source="editor_parse",
                    severity=Severity.WARNING,
                    message="Failed to parse EditorAgent JSON response"
                )
            )
            state["morning_note"] = None
            state["recommendation"] = None
            state["confidence_scores"] = {}
            state["data_freshness"]["editor"] = datetime.now(UTC)
            return state
    else:
        state["flags"].append(
            DataFlag(
                source="editor_parse",
                severity=Severity.WARNING,
                message="Missing keys"
            )
        )
        state["morning_note"] = None
        state["recommendation"] = None
        state["confidence_scores"] = {}
        state["data_freshness"]["editor"] = datetime.now(UTC)
        return state

    state["morning_note"] = parsed["morning_note"]
    state["recommendation"] = parsed["recommendation"]
    state["confidence_scores"] = parsed["confidence_scores"]
    state["data_freshness"]["editor"] = datetime.now(UTC)
    return state
