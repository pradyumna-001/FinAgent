# app/agents/macro.py

import os
import logging
import re
from datetime import datetime, timezone

from openai import OpenAI
from tavily import TavilyClient

from app.graph.state import AgentState, MacroOutput
from app.utils.data_preprocessing import DataFlag
from app.prompts.services.prompt_loader import PromptManagementService

logger = logging.getLogger("finagent.agents.macro")

def macro_agent_node(state: AgentState) -> AgentState:
    """
    MacroAgent Node:
    1. Gathers live Brazilian economic context using the Tavily Search API.
    2. Synthesizes and extracts GDP, Inflation, and Interest Rates using OpenRouter (Llama 3.3 70B).
    3. Guarantees structured JSON output mapping to our Pydantic MacroOutput schema.
    4. Records execution metadata and handles external API failures gracefully.
    """
    run_id = state.get("pipeline_run_id", "UNKNOWN_RUN")
    note_id = state.get("morning_note_id", "UNKNOWN_NOTE")

    logger.info(f"[{run_id}][{note_id}] Starting MacroAgent analysis.")

    # 1. Fetch credentials
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    tavily_api_key = os.getenv("TAVILY_API_KEY")

    if not openrouter_api_key or not tavily_api_key:
        error_msg = "Missing API Keys. Please configure OPENROUTER_API_KEY and TAVILY_API_KEY"
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
    
    # 2. Gather market context via Tavily Search
    search_query = (
        "últimos dados Brasil economia PIB taxa Selic inflação IPCA "
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

    # 3. Load and format Prompt
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
    
    # 4. Request structured reasoning and schema formatting from OpenRouter
    try:
        logger.info(f"[{run_id}][{note_id}] Requesting structured output from OpenRouter...")
        
        # Configure the client to point to the OpenRouter gateway endpoint
        client = OpenAI(
            api_key=openrouter_api_key,
            base_url="https://openrouter.ai/api/v1"
        )

        # Target Meta's flagship free 70B model
        target_model = "openrouter/free"

        # Explicitly instruct the model to return raw JSON matching our schema
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
            # Enforce dynamic json object schema formatting support
            response_format={
                "type": "json_object"
            },
            temperature=0.1
        )

        raw_content = response.choices[0].message.content.strip()        

        # Validate raw output matches our Pydantic structure exactly
        cleaned_content = raw_content
        if cleaned_content.startswith("```"):
            # Strip off the ```json or ``` and trailing ```
            cleaned_content = re.sub(r"^```(?:json)?\n", "", cleaned_content, flags=re.IGNORECASE)
            cleaned_content = re.sub(r"\n```$", "", cleaned_content)
            cleaned_content = cleaned_content.strip()
        
        # Validate that the cleaned output matches our Pydantic structure exactly
        macro_data = MacroOutput.model_validate_json(cleaned_content)
        state["macro_context"] = macro_data

        # Set metadata map freshness safely
        if "data_freshness" not in state:
            state["data_freshness"] = {}
        state["data_freshness"]["macro"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"[{run_id}][{note_id}] MacroAgent successfully completed analysis.")

    except Exception as model_err:
        fail_msg = f"OpenRouter generation or validation failed: {str(model_err)}"
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