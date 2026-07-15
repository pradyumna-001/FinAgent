import os
import logging
from datetime import datetime, timezone
from google import genai
from google.genai import types
from google.genai.errors import APIError
from tavily import TavilyClient

from app.graph.state import AgentState, MacroOutput
from app.utils.data_preprocessing import DataFlag

logger = logging.getLogger("finagent.agents.macro")

def macro_agent_node(state: AgentState) -> AgentState:
    """
    MacroAgent Node:
    1. Gathers live Brazilian economic context using the Tavily Search API.
    2. Synthesizes and extracts GDP, Inflation, and Interest Rates using Gemini.
    3. Guarantees structured JSON output mapping to our Pydantic MacroOutput schema.
    4. Records execution metadata and handles external API failures gracefully.
    """
    run_id = state.get("pipeline_run_id", "UNKNOWN_RUN")
    note_id = state.get("morning_note_id", "UNKNOWN_NOTE")

    logger.info(f"[{run_id}][{note_id}] Starting MacroAgent analysis.")

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    tavily_api_key = os.getenv("TAVILY_API_KEY")

    if not gemini_api_key or not tavily_api_key:
        error_msg = "Missing API Keys. Please configure GEMIN_API_KEY and TAVILY_API_KEY"
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
    
    search_query = (
        "últimos dados Brasil economia PIB taxa Selic inflação IPCA"
        "Banco Central IBGE Reuters Brasil Bloomberg"
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

    current_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(current_dir)
    prompt_path = os.path.join(app_dir, "prompts", "macro_agent.txt")

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
        prompt = prompt_template.format(search_results=search_results)
    except FileNotFoundError as fnf_err:
        fail_msg = f"Prompt template file not found at {prompt_path}: {str(fnf_err)}"
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
        logger.info(f"[{run_id}][{note_id}] Requesting structured output from Gemini...")
        client = genai.Client(api_key=gemini_api_key)

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MacroOutput,
                temperature=0.1,
            ),
        )

        macro_data = MacroOutput.model_validate_json(response.text)

        state["macro_context"] = macro_data
        state["data_freshness"]["macro"] = datetime.now(timezone.utc)
        logger.info(f"[{run_id}][{note_id}] MacroAgent successfully completed analysis.")

    except (APIError, Exception) as model_err:
        fail_msg = f"Gemini content generation or schema validation failed: {str(model_err)}"
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
