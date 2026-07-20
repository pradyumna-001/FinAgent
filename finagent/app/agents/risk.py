import logging
import os
import re
import json
from datetime import datetime, timezone

from app.core.config import get_llm_client, settings
from app.graph.state import AgentState, RiskFlag
from app.prompts.services.prompt_loader import PromptManagementService
from app.utils.data_preprocessing import DataFlag

logger = logging.getLogger("finagent.agents.risk")

def risk_agent_node(state: AgentState) -> AgentState:
    run_id = state.get("pipeline_run_id", "UNKNOWN_RUN")
    note_id = state.get("morning_note_id", "UNKNOWN_NOTE")
    ticker = state.get("company_ticker", "UNKNOWN_TICKER")

    logger.info(f"[{run_id}][{note_id}] Starting RiskAgent analysis for {ticker}.")

    nvidia_api_key = os.getenv("NVIDIA_API_KEY") or settings.nvidia_api_key

    if not nvidia_api_key:
        error_msg = "Missing API Key. Please configure NVIDIA_API_KEY"
        logger.error(f"[{run_id}][{note_id}] {error_msg}")

        state["flags"].append(
            DataFlag(
                source="risk_agent",
                flag_type="high",
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={"error": error_msg}
            )
        )
        state["risk_flags"] = []
        return state

    # Extract accumulated pipeline contexts to hand over to the adversarial analyzer
    macro_ctx = state.get("macro_context")
    quant_metrics = state.get("quant_metrics")
    company_events = state.get("company_events", [])
    active_flags = state.get("flags", [])

    # Format pipeline data gaps explicitly to serve as additional threat vectors
    data_gaps_payload = ""
    if active_flags:
        data_gaps_payload = "\nCRITICAL DATA GAPS DETECTED IN PIPELINE:\n" + "\n".join(
            [f"- Source: {f.source} | Error context: {f.metadata.get('error', 'unknown')}" for f in active_flags]
        )

    analysis_payload = {
        "ticker": ticker,
        "macro_context": macro_ctx.model_dump() if macro_ctx else None,
        "quant_metrics": quant_metrics.model_dump() if quant_metrics else None,
        "company_events": [e.model_dump() for e in company_events],
        "data_gaps_and_omissions": data_gaps_payload
    }

    try:
        prompt_service = PromptManagementService()
        
        system_template = prompt_service.load_prompt("risk_agent_system")
        user_template = prompt_service.load_prompt("risk_agent_user")

        schema_instruction = (
            f"You must return a valid JSON object with a single key 'risks' containing a list of objects. "
            f"Each object in the list must match this schema exactly: {RiskFlag.model_json_schema()}"
        )

        system_prompt = system_template.format({"schema_instruction": schema_instruction})
        user_prompt = user_template.format({
            "ticker": ticker,
            "pipeline_context": json.dumps(analysis_payload, indent=2, default=str)
        })

    except (FileNotFoundError, ValueError, KeyError) as prompt_err:
        fail_msg = f"Prompt service failure: {str(prompt_err)}"
        logger.error(f"[{run_id}][{note_id}] {fail_msg}")

        state["flags"].append(
            DataFlag(
                source="risk_agent",
                flag_type="high",
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={"error": fail_msg}
            )
        )
        return state

    try:
        logger.info(f"[{run_id}][{note_id}] Requesting structured adversarial output from NVIDIA...")

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
        risks_list = parsed_json.get("risks", [])

        validated_risks = [RiskFlag.model_validate(risk) for risk in risks_list]
        state["risk_flags"].extend(validated_risks)

        if "data_freshness" not in state:
            state["data_freshness"] = {}
        state["data_freshness"]["risk"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"[{run_id}][{note_id}] RiskAgent successfully completed adversarial analysis loop.")

    except Exception as model_err:
        fail_msg = f"NVIDIA generation, parsing, or validation failed: {str(model_err)}"
        logger.error(f"[{run_id}][{note_id}] {fail_msg}")

        state["flags"].append(
            DataFlag(
                source="risk_agent",
                flag_type="high",
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={"error": fail_msg}
            )
        )

    return state
