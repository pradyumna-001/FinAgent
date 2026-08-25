from datetime import datetime, UTC
import logging

from app.prompts.risk import RISK_PROMPTS
from app.services.llm import summarize
from app.graph.state import AgentState
from app.utils.risk_parse import parse_risk_json
from app.utils.flags import DataFlag, Severity


logger = logging.getLogger(__name__)


async def risk_agent_node(state: AgentState) -> dict:
    """Read upstream agent products, call the LLM for adversarial risk analysis, and stage 
    the raw response for parsing. Failures append a DataFlag and return with risk_flags=[] - never raises.
    """
    logger.info(
        "risk_agent_start",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "morning_note_id": state["morning_note_id"],
            "manager_id": state["manager_id"]
        }
    )

    await state["sse_service"].emit_event(
        state["pipeline_run_id"],
        {
            "event_type": "agent_started",
            "agent_name": "risk",
            "timestamp": datetime.now(UTC).isoformat()
        }
    )

    user_prompt = RISK_PROMPTS.build_user_prompt(
        macro_context=state.get("macro_context"),
        company_events=state.get("company_events", []),
        quant_metrics=state.get("quant_metrics"),
        data_flags=state.get("flags", [])
    )

    raw_text = await summarize(
        system=RISK_PROMPTS.system,
        user=user_prompt
    )

    flags, dropped = parse_risk_json(raw_text)
    new_flags = []
    if dropped > 0 or raw_text is None:
        new_flags.append(
            DataFlag(
                source="risk_parse",
                severity=Severity.WARNING,
                message=f"{dropped} risk flag(s) dropped during parsing",
            )
        )

    confidence = state["confidence_scores"].get("risk", 1.0)
    await state["sse_service"].emit_event(
        state["pipeline_run_id"],
        {
            "event_type": "agent_completed",
            "agent_name": "risk",
            "confidence_score": confidence,
            "timestamp": datetime.now(UTC).isoformat()
        }
    )
    return {
        "risk_flags": flags,
        "data_freshness": {"risk": datetime.now(UTC)},
        "flags": new_flags
    }
