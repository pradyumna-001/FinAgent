from datetime import datetime, UTC

import logging

from app.core.config import settings
from app.graph.state import AgentState, CompanyEvent
from app.prompts.company import COMPANY_PROMPTS
from app.services.llm import summarize
from app.services.tavily import TavilyService, TavilyConfigError
from app.utils.flags import DataFlag, Severity


logger = logging.getLogger(__name__)


async def company_agent_node(state: AgentState) -> AgentState:
    """Pull company news via TavilyService for ticker in state, extract
    CompanyEvents via NVIDIA NIM, and update AgentState in-place.
    Failures append a DataFlag and return - never raises.
    """
    logger.info(
        "company_agent_start",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "morning_note_id": state["morning_note_id"],
            "manager_id": state["manager_id"]
        }
    )

    try:
        tavily = TavilyService(api_key=settings.TAVILY_API_KEY)
    except TavilyConfigError as exc:
        state["flags"].append(
            DataFlag(
                source="tavily",
                severity=Severity.FATAL,
                message=str(exc)
            )
        )
        state["company_events"] = []
        state["data_freshness"]["company"] = datetime.now(UTC)
        return state

    ticker = state["company_ticker"]
    result = await tavily.search(
        query=f"{ticker} news Brazil",
        include_domains=[
            "cvm.gov.br",
            "infomoney.com.br",
            "globo.com/valor-economico"
        ],
        max_results=10
    )
    if result.error:
        state["flags"].append(result.error)
        state["company_events"] = []
        state["data_freshness"]["company"] = datetime.now(UTC)
        return state

    company_events: list[CompanyEvent] = []
    if result.articles:
        top = result.articles[0]
        raw_text = f"{top.title or ''}\n\n{top.content or ''}\n{top.url or ''}"

        summary = await summarize(
            system=COMPANY_PROMPTS.system,
            user=COMPANY_PROMPTS.build_user_prompt(raw_text=raw_text)
        )

        if summary is None:
            state["flags"].append(
                DataFlag(
                    source="nvidia_nim",
                    severity=Severity.WARNING,
                    message="Summarization returned None; using raw content"
                )
            )
            summary = top.content or ""

        company_events.append(
            CompanyEvent(
                title=top.title or "",
                date="",
                source=top.url or "",
                summary=summary
            )
        )

    state["company_events"] = company_events
    state["data_freshness"]["company"] = datetime.now(UTC)
    return state
