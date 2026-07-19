import os
import logging
import re
import json
from datetime import datetime, timezone

from openai import OpenAI

from app.graph.state import AgentState, Recommendation, EditorOutputSchema
from app.utils.data_preprocessing import DataFlag
from app.prompts.services.prompt_loader import PromptManagementService

logger = logging.getLogger("finagent.agents.editor")

def editor_agent_node(state: AgentState) -> AgentState:
    run_id = state.get("pipeline_run_id", "UNKNOWN_RUN")
    note_id = state.get("morning_note_id", "UNKNOWN_NOTE")
    ticker = state.get("company_ticker", "UNKNOWN_TICKER")

    logger.info(f"[{run_id}][{note_id}] Starting EditorAgent compilation for {ticker}...")

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

    if not openrouter_api_key:
        error_msg = "Missing API Key. Please configure OPENROUTER_API_KEY"
        logger.error(f"[{run_id}][{note_id}] {error_msg}")

        state["flags"].append(
            DataFlag(
                source="editor_agent",
                flag_type="high",
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={"error": error_msg}
            )
        )
        state["morning_note"] = None
        state["recommendation"] = None
        return state

    active_flags = state.get("flags", [])
    failed_sources = {f.source for f in active_flags}

    confidence_scores = {
        "macro": 0.4 if "macro_agent" in failed_sources else 0.9,
        "company": 0.4 if "company_agent" in failed_sources else 0.9,
        "quant": 0.4 if "quant_agent" in failed_sources else 0.9,
        "risk": 0.4 if "risk_agent" in failed_sources else 0.9,
    }
    state["confidence_scores"] = confidence_scores

    macro_ctx = state.get("macro_context")
    quant_metrics = state.get("quant_metrics")
    company_events = state.get("company_events", [])
    risk_flags = state.get("risk_flags", [])
    
    analysis_payload = {
        "ticker": ticker,
        "macro_context": macro_ctx.model_dump() if macro_ctx else None,
        "quant_metrics": quant_metrics.model_dump() if quant_metrics else None,
        "company_events": [e.model_dump() for e in company_events],
        "risk_flags": [r.model_dump() for r in risk_flags],
        "pipeline_confidence_scores": confidence_scores,
        "has_data_gaps": len(active_flags) > 0
    }

    try:
        prompt_service = PromptManagementService()

        system_template = prompt_service.load_prompt("editor_agent_system")
        user_template = prompt_service.load_prompt("editor_agent_user")

        schema_instruction = (
            f"You must return a valid JSON object matching this schema blueprint exactly: "
            f"{EditorOutputSchema.model_json_schema()}. "
            f"The morning_note field must be a markdown-formatted string in Portuguese containing "
            f"all required sections. If has_data_gaps is true or any section confidence is < 0.5, "
            f"you MUST prepend an uppercase warning banner '⚠️ [AVISO DE LACUNA DE DADOS]' into that section."
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
                source="editor_agent",
                flag_type="high",
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={"error": fail_msg}
            )
        )
        return state
    
    try:
        logger.info(f"[{run_id}][{note_id}] Requesting consolidated morning note from OpenRouter...")

        client = OpenAI(
            api_key=openrouter_api_key,
            base_url="https://openrouter.ai/api/v1"
        )

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={
                "type": "json_object"
            },
            temperature=0.2
        )

        raw_content = response.choices[0].message.content.strip()

        cleaned_content = raw_content
        if cleaned_content.startswith("```"):
            cleaned_content = re.sub(r"^```(?:json)?\n", "", cleaned_content, flags=re.IGNORECASE)
            cleaned_content = re.sub(r"\n```$", "", cleaned_content)
            cleaned_content = cleaned_content.strip()

        parsed_json = json.loads(cleaned_content)
        validated_output = EditorOutputSchema.model_validate(parsed_json)

        state["morning_note"] = validated_output.morning_note
        state["recommendation"] = Recommendation(
            action=validated_output.action,
            target_weight=validated_output.target_weight,
            horizon_months=validated_output.horizon_months,
            thesis_summary=validated_output.thesis_summary
        )

        if "data_freshness" not in state:
            state["data_freshness"] = {}
        state["data_freshness"]["editor"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"[{run_id}][{note_id}] EditorAgent successfully compiled the investment morning note.")

    except Exception as model_err:
        fail_msg = f"OpenRouter validation or distillation failed: {str(model_err)}"
        logger.error(f"[{run_id}][{note_id}] {fail_msg}")

        state["flags"].append(
            DataFlag(
                source="editor_agent",
                flag_type="high",
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={"error": fail_msg}
            )
        )

    return state
