import logging
import os
import re
import json
from datetime import datetime, timezone

from tavily import TavilyClient

from app.core.config import get_llm_client, settings
from app.graph.state import AgentState, CompanyEvent
from app.prompts.services.prompt_loader import PromptManagementService
from app.utils.data_preprocessing import DataFlag

MONTHS_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
}

logger = logging.getLogger("finagent.agents.company")

def company_agent_node(state: AgentState) -> AgentState:
    run_id = state.get("pipeline_run_id", "UNKNOWN_RUN")
    note_id = state.get("morning_note_id", "UNKNOWN_NOTE")
    ticker = state.get("company_ticker", "UNKNOWN_TICKER")

    logger.info(f"[{run_id}][{note_id}] Starting CompanyAgent analysis for {ticker}.")

    nvidia_api_key = os.getenv("NVIDIA_API_KEY") or settings.nvidia_api_key
    tavily_api_key = os.getenv("TAVILY_API_KEY") or settings.tavily_api_key

    if not nvidia_api_key or not tavily_api_key:
        error_msg = "Missing API Keys. Please configure NVIDIA_API_KEY and TAVILY_API_KEY"
        logger.error(f"[{run_id}][{note_id}] {error_msg}")

        state["flags"].append(
            DataFlag(
                source="company_agent",
                flag_type="high",
                message=error_msg,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        )
        state["company_events"] = []
        return state

    now = datetime.now(timezone.utc)
    month_name = MONTHS_PT[now.month]
    year_str = str(now.year)

    search_query = (
        f"ticker {ticker} fatos relevantes CVM notícias "
        f"InfoMoney Valor Econômico {month_name} {year_str}"
    )

    try:
        logger.info(f"[{run_id}][{note_id}] Executing Tavily Search for {ticker}...")
        tavily_client = TavilyClient(api_key=tavily_api_key)

        search_results = tavily_client.get_search_context(
            query=search_query,
            search_depth="advanced",
            max_results=5
        )
    except Exception as search_err:
        fail_msg = f"Tavily search failed for {ticker}: {str(search_err)}"
        logger.error(f"[{run_id}][{note_id}] {fail_msg}")

        state["flags"].append(
            DataFlag(
                source="company_agent",
                flag_type="high",
                message=fail_msg,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        )
        state["company_events"] = []
        return state

    try:
        prompt_service = PromptManagementService()

        system_template = prompt_service.load_prompt("company_agent_system")
        user_template = prompt_service.load_prompt("company_agent_user")

        schema_instruction = (
            f"You must return a valid JSON object with a single key 'events' containing a list of objects"
            f"Each object in the list must match this schema: {CompanyEvent.model_json_schema()}"
        )

        system_prompt = system_template.format({"schema_instruction": schema_instruction})
        user_prompt = user_template.format({
            "ticker": ticker,
            "search_results": search_results
        })

    except (FileNotFoundError, ValueError, KeyError) as prompt_err:
        fail_msg = f"Prompt service failure: {str(prompt_err)}"
        logger.error(f"[{run_id}][{note_id}] {fail_msg}")

        state["flags"].append(
            DataFlag(
                source="company_agent",
                flag_type="high",
                message=fail_msg,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        )
        state["company_events"] = []
        return state

    try:
        logger.info(f"[{run_id}][{note_id}] Requesting structured output from NVIDIA...")

        client = get_llm_client()
        target_model = os.getenv("NVIDIA_MODEL", settings.nvidia_model)

        response = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={
                "type": "json_object"
            },
            temperature=0.1
        )

        raw_content = response.choices[0].message.content.strip()

        cleaned_content = raw_content
        if cleaned_content.startswith("```"):
            cleaned_content = re.sub(r"^```(?:json)?\n", "", cleaned_content, flags=re.IGNORECASE)
            cleaned_content = re.sub(r"\n```$", "", cleaned_content)
            cleaned_content = cleaned_content.strip()

        parsed_json = json.loads(cleaned_content)
        events_list = parsed_json.get("events", [])

        validated_events = [CompanyEvent.model_validate(event) for event in events_list]
        state["company_events"] = validated_events

        if "data_freshness" not in state:
            state["data_freshness"] = {}
        state["data_freshness"]["company"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"[{run_id}][{note_id}] CompanyAgent successfully completed analysis.")

    except Exception as model_err:
        fail_msg = f"NVIDIA generation, parsing, or validation failed: {str(model_err)}"
        logger.error(f"[{run_id}][{note_id}] {fail_msg}")

        state["flags"].append(
            DataFlag(
                source="company_agent",
                flag_type="high",
                message=fail_msg,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        )
        state["company_events"] = []

    return state
