from datetime import datetime, UTC

import logging

from app.core.config import settings
from app.graph.state import AgentState, MacroOutput
from app.prompts.macro import MACRO_PROMPTS
from app.services.llm import summarize
from app.services.tavily import TavilyService, TavilyConfigError
from app.utils.flags import DataFlag, Severity


logger = logging.getLogger(__name__)


async def macro_agent_node(state: AgentState) -> dict:
    """Pull macro-news via TavilyService, build a MacroOutput, and update
    AgentState in-place. Failures append a DataFlag and returns
    with macro_context=None - never raises.
    """
    logger.info(
        "macro_agent_start",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "morning_note_id": state["morning_note_id"],
            "manager_id": state["manager_id"]
        }
    )

    new_flags = []

    try:
        tavily = TavilyService(api_key=settings.TAVILY_API_KEY)
    except TavilyConfigError as exc:
        new_flags.append(
            DataFlag(
                source="tavily",
                severity=Severity.FATAL,
                message=str(exc)
            )
        )
        return {
            "macro_context": None,
            "data_freshness": {"macro": datetime.now(UTC)},
            "flags": new_flags
        }

    result = await tavily.search(
        query="macro news Brazil",
        include_domains=[
            "bcb.gov.br", 
            "ibge.gov.br", 
            "br.reuters.com", 
            "bloomberg.com.br"
        ],
        max_results=10
    )
    if result.error:
        new_flags.append(result.error)
        return {
            "macro_context": None,
            "data_freshness": {"macro": datetime.now(UTC)},
            "flags": new_flags
        }

    macro_output: MacroOutput | None = None
    if result.articles:
        top = result.articles[0]
        raw_text = f"{top.title or ''}\n\n{top.content or ''}\n{top.url or ''}"

        summary = await summarize(
            system=MACRO_PROMPTS.system,
            user=MACRO_PROMPTS.build_user_prompt(raw_text=raw_text)
        )

        if summary is None:
            new_flags.append(
                DataFlag(
                    source="nvidia_nim",
                    severity=Severity.WARNING,
                    message="Summarization returned None; using raw content"
                )
            )
            summary = top.content or ""

        macro_output = MacroOutput(
            headline=top.title or "",
            summary=summary,
            sources=[top.url] if top.url else [],
            fetched_at=datetime.now(UTC).isoformat()
        )

    return {
        "macro_context": macro_output,
        "data_freshness": {"macro": datetime.now(UTC)},
        "flags": new_flags
    }
