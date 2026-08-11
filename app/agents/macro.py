from datetime import datetime, UTC
import logging

import httpx

from app.core.config import settings
from app.graph.state import AgentState, MacroOutput
from app.prompts.macro import MACRO_PROMPTS
from app.services.llm import summarize
from app.utils.flags import DataFlag, Severity

logger = logging.getLogger(__name__)


async def macro_agent_node(state: AgentState) -> AgentState:
    """Pull macro-news via Tavily, build a MacroOutput, and update
    the AgentState in-place. Failures append a DataFlag and return
    with macro_context=None — never raises.
    """
    logger.info(
        "macro_agent_start",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "morning_note_id": state["morning_note_id"],
            "manager_id": state["manager_id"],
        },
    )

    tavily_key = settings.TAVILY_API_KEY
    if not tavily_key:
        state["flags"].append(
            DataFlag(
                source="tavily",
                severity=Severity.FATAL,
                message="TAVILY_API_KEY missing",
            )
        )
        state["macro_context"] = None
        state["data_freshness"]["macro"] = datetime.now(UTC)
        return state

    payload = {"query": "macro news Brazil", "max_results": 10,
               "include_domains": ["bcb.gov.br", "ibge.gov.br", "br.reuters.com", "bloomberg.com.br"]}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {tavily_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        state["flags"].append(
            DataFlag(
                source="tavily",
                severity=Severity.WARNING,
                message=f"Tavily request error: {exc}",
            )
        )
        state["macro_context"] = None
        state["data_freshness"]["macro"] = datetime.now(UTC)
        return state

    macro_output: MacroOutput | None = None
    if data and data.get("results"):
        top = data["results"][0]
        raw_text = (
            f"{top.get('title', '')}\n\n"
            f"{top.get('content', '')}\n{top.get('url', '')}"
        )

        summary = await summarize(
            system=MACRO_PROMPTS.system,
            user=MACRO_PROMPTS.build_user_prompt(raw_text=raw_text),
        )

        if summary is None:
            state["flags"].append(
                DataFlag(
                    source="tavily",
                    severity=Severity.WARNING,
                    message="Summarization returned None; using raw content.",
                )
            )
            summary = top.get("content", "")

        macro_output = MacroOutput(
            headline=str(top.get("title", "")),
            summary=summary,
            sources=[str(top.get("url", ""))] if top.get("url") else [],
            fetched_at=datetime.now(UTC).isoformat(),
        )

    state["macro_context"] = macro_output
    state["data_freshness"]["macro"] = datetime.now(UTC)
    return state