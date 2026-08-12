from datetime import datetime, UTC

import logging
import httpx

from app.core.config import settings
from app.graph.state import AgentState, CompanyEvent
from app.prompts.company import COMPANY_PROMPTS
from app.services.llm import summarize
from app.utils.flags import DataFlag, Severity


logger = logging.getLogger(__name__)


async def company_agent_node(state: AgentState) -> AgentState:
    """Pull company news via Tavily for the ticker in state, extract
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


    tavily_key = settings.TAVILY_API_KEY
    if not tavily_key:
        state["flags"].append(
            DataFlag(
                source="tavily",
                severity=Severity.FATAL,
                message="TAVILY_API_KEY missing"
            )
        )
        state["company_events"] = []
        state["data_freshness"]["company"] = datetime.now(UTC)
        return state


    ticker = state["company_ticker"]
    payload = {
        "query": f"{ticker} news Brazil",
        "max_results": 10,
        "include_domains": [
            "cvm.gov.br",
            "infomoney.com.br",
            "globo.com/valor-economico"
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {tavily_key}"},
                json=payload
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        state["flags"].append(
            DataFlag(
                source="tavily",
                severity=Severity.WARNING,
                message=f"Tavily request error: {exc}"
            )
        )
        state["company_events"] = []
        state["data_freshness"]["company"] = datetime.now(UTC)
        return state


    company_events: list[CompanyEvent] = []
    try:
        if not data or not data.get("results"):
            raise ValueError("Tavily returned no results field")
        top = data["results"][0]
        if not (top.get("title") and top.get("content")):
            raise ValueError(
                f"Tavily returned results with null title/content for "
                f"{ticker} - schema may have changed"
            )
        raw_text = (
            f"{top.get('title', '')}\n\n"
            f"{top.get('content', '')}\n{top.get('url', '')}"
        )

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
            summary = top.get("content", "")

        company_events.append(
            CompanyEvent(
                title=str(top.get("title", "")),
                date="",
                source=str(top.get("url", "")),
                summary=summary
            )
        )
    except (ValueError, KeyError, IndexError) as exc:
        state["flags"].append(
            DataFlag(
                source="tavily",
                severity=Severity.FATAL,
                message=f"parse-block failed for {state['company_ticker']}: {exc}"
            )
        )
        state["company_events"] = []
        state["data_freshness"]["company"] = datetime.now(UTC)
        return state

    state["company_events"] = company_events
    state["data_freshness"]["company"] = datetime.now(UTC)
    return state