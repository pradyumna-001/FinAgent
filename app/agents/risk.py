from datetime import datetime, UTC
import logging

from app.prompts.risk import RISK_PROMPTS
from app.services.llm import summarize
from app.graph.state import AgentState


logger = logging.getLogger(__name__)


async def risk_agent_node(state: AgentState) -> AgentState:
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

    state["risk_flags"] = []
    state["data_freshness"]["risk"] = datetime.now(UTC)
    return state
