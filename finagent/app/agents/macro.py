import logging
import os
import re
from datetime import datetime, timezone

from tavily import TavilyClient

from app.core.config import get_llm_client, settings
from app.graph.state import AgentState, MacroOutput
from app.prompts.services.prompt_loader import PromptManagementService
from app.utils.data_preprocessing import DataFlag

MONTHS_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
}

logger = logging.getLogger("finagent.agents.macro")

def macro_agent_node(state: AgentState) -> AgentState:
    run_id = state.get("pipeline_run_id", "UNKNOWN_RUN")
    note_id = state.get("morning_note_id", "UNKNOWN_NOTE")

    logger.info(f"[{run_id}][{note_id}] Starting MacroAgent analysis.")

    nvidia_api_key = os.getenv("NVIDIA_API_KEY") or settings.nvidia_api_key
    tavily_api_key = os.getenv("TAVILY_API_KEY") or settings.tavily_api_key

    if not nvidia_api_key or not tavily_api_key:
        error_msg = "Missing API Keys. Please configure NVIDIA_API_KEY and TAVILY_API_KEY"
        logger.error(f"[{run_id}][{note_id}] {error_msg}")

        state["flags"].append(
            DataFlag(
                source="macro_agent",
                flag_type="high",
                message=error_msg,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        )
        state["macro_context"] = None
        return state

    now = datetime.now(timezone.utc)
    month_name = MONTHS_PT[now.month]
    year_str = str(now.year)

    search_query = (
        f"últimos dados oficiais economia Brasil {month_name} {year_str} "
        f"PIB inflação IPCA taxa Selic Banco Central IBGE"
    )

    try:
        logger.info(f"[{run_id}][{note_id}] Executing Tavily Search...")
        tavily_client = TavilyClient(api_key=tavily_api_key)

        search_results = tavily_client.get_search_context(
            query=search_query,
            search_depth="advanced",
            max_results=5
        )
    except Exception as search_err:
        fail_msg = f"Tavily search failed: {str(search_err)}"
        logger.error(f"[{run_id}][{note_id}] {fail_msg}")

        state["flags"].append(
            DataFlag(
                source="macro_agent",
                flag_type="high",
                message=fail_msg,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        )
        state["macro_context"] = None
        return state

    try:
        prompt_service = PromptManagementService()
        template = prompt_service.load_prompt("macro_agent")
        prompt = template.format({"search_results": search_results})
    except (FileNotFoundError, ValueError, KeyError) as prompt_err:
        fail_msg = f"Prompt service failure: {str(prompt_err)}"
        logger.error(f"[{run_id}][{note_id}] {fail_msg}")

        state["flags"].append(
            DataFlag(
                source="macro_agent",
                flag_type="high",
                message=fail_msg,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        )
        state["macro_context"] = None
        return state

    try:
        logger.info(f"[{run_id}][{note_id}] Requesting structured output from NVIDIA...")

        client = get_llm_client()
        target_model = os.getenv("NVIDIA_MODEL", settings.nvidia_model)

        schema_instruction = (
            f"You must return a valid JSON object matching this schema: "
            f"{MacroOutput.model_json_schema()}"
        )

        response = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": f"You are a strict financial analyst. {schema_instruction}"},
                {"role": "user", "content": prompt}
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

        macro_data = MacroOutput.model_validate_json(cleaned_content)
        state["macro_context"] = macro_data

        if "data_freshness" not in state:
            state["data_freshness"] = {}
        state["data_freshness"]["macro"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"[{run_id}][{note_id}] MacroAgent successfully completed analysis.")

    except Exception as model_err:
        fail_msg = f"NVIDIA generation or validation failed: {str(model_err)}"
        logger.error(f"[{run_id}][{note_id}] {fail_msg}")

        state["flags"].append(
            DataFlag(
                source="macro_agent",
                flag_type="high",
                message=fail_msg,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        )
        state["macro_context"] = None

    return state
