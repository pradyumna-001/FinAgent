import json
import logging
from datetime import UTC, datetime

from app.graph.state import AgentState
from app.prompts.editor import EDITOR_PROMPTS
from app.services.llm import summarize_nemotron
from app.services.sse import sse_service
from app.utils.editor_confidence import apply_confidence_penalties
from app.utils.flags import DataFlag, Severity

logger = logging.getLogger(__name__)


async def editor_agent_node(state: AgentState) -> dict:
    logger.info(
        "editor_agent_start",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "morning_note_id": state["morning_note_id"],
            "manager_id": state["manager_id"],
            "flags": state["flags"]
        }
    )

    new_flags: list[DataFlag] = []

    raw_flags = state.get("flags", [])
    for f in raw_flags:
        if isinstance(f, DataFlag):
            new_flags.append(f)
        elif isinstance(f, dict) and "source" in f:
            sev = f["severity"]
            if isinstance(sev, Severity):
                severity = sev
            else:
                severity = Severity(sev)
            new_flags.append(DataFlag(
                source=f["source"],
                severity=severity,
                message=f["message"],
            ))
        else:
            logger.warning("invalid_flag_in_state", extra={"flag": f})

    tickers = state.get("company_tickers", [])

    if not tickers:
        confidence = state["confidence_scores"].get("editor", 1.0)
        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "agent_completed",
                "agent_name": "editor",
                "confidence_score": confidence,
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "note_ready",
                "morning_note_id": state["morning_note_id"],
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        sse_service.cleanup(state["pipeline_run_id"])
        return {
            "morning_note": "Nenhuma empresa no portfólio para gerar morning note.",
            "recommendations": {},
            "confidence_scores": {},
            "data_freshness": {"editor": datetime.now(UTC)},
            "flags": new_flags
        }

    # Emit agent_started once (Editor runs once after consolidate, not in fan-out)
    await sse_service.emit_event(
        state["pipeline_run_id"],
        {
            "event_type": "agent_started",
            "agent_name": "editor",
            "timestamp": datetime.now(UTC).isoformat()
        }
    )

    data_flags = [f for f in new_flags if isinstance(f, DataFlag)]
    
    user_prompt = EDITOR_PROMPTS.build_user_prompt(
        macro_context=state.get("macro_context", {}),
        company_tickers=tickers,
        company_events=state.get("company_events", {}),
        quant_metrics=state.get("quant_metrics", {}),
        risk_flags=state.get("risk_flags", {}),
        portfolio_risk_flags=state.get("portfolio_risk_flags", []),
        portfolio_data_flags=state.get("portfolio_data_flags", []),
        sector_weights=state.get("sector_weights", {}),
        data_flags=data_flags,
        data_freshness=state.get("data_freshness", {})
    )

    raw_text = await summarize_nemotron(
        system=EDITOR_PROMPTS.system,
        user=user_prompt
    )

    if raw_text is None:
        new_flags.append(
            DataFlag(
                source="summarize_nemotron",
                severity=Severity.FATAL,
                message="Summarization failed for editor"
            )
        )
        recommendations: dict[str, dict] = {}
        confidence_scores: dict[str, dict[str, float]] = {}
        morning_note_sections: list[str] = []
        
        for t in tickers:
            recommendations[t] = {}
            confidence_scores[t] = {}
            morning_note_sections.append(f"### {t}\n\n[Dados indisponíveis para {t}]")
        
        morning_note = "\n\n".join(morning_note_sections)
        all_new_flags = list(new_flags)
        penalized_confidence_scores, all_warnings = apply_confidence_penalties(confidence_scores, all_new_flags)
        
        if all_warnings:
            morning_note = "\n\n".join(all_warnings) + "\n\n" + morning_note
        
        confidence = state["confidence_scores"].get("editor", 1.0)
        
        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "agent_completed",
                "agent_name": "editor",
                "confidence_score": confidence,
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "note_ready",
                "morning_note_id": state["morning_note_id"],
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        
        sse_service.cleanup(state["pipeline_run_id"])
        
        return {
            "morning_note": morning_note,
            "recommendations": recommendations,
            "confidence_scores": penalized_confidence_scores,
            "data_freshness": {"editor": datetime.now(UTC)},
            "flags": all_new_flags
        }

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        new_flags.append(
            DataFlag(
                source="editor_parse",
                severity=Severity.WARNING,
                message="Failed to parse EditorAgent JSON response"
            )
        )
        
        recommendations: dict[str, dict] = {}
        confidence_scores: dict[str, dict[str, float]] = {}
        morning_note_sections: list[str] = []
        
        for t in tickers:
            recommendations[t] = {}
            confidence_scores[t] = {}
            morning_note_sections.append(f"### {t}\n\n[Dados indisponíveis para {t}]")
        
        morning_note = "\n\n".join(morning_note_sections)
        all_new_flags = list(new_flags)
        penalized_confidence_scores, all_warnings = apply_confidence_penalties(confidence_scores, all_new_flags)
        
        if all_warnings:
            morning_note = "\n\n".join(all_warnings) + "\n\n" + morning_note
        
        confidence = state["confidence_scores"].get("editor", 1.0)
        
        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "agent_completed",
                "agent_name": "editor",
                "confidence_score": confidence,
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        
        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "note_ready",
                "morning_note_id": state["morning_note_id"],
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        
        sse_service.cleanup(state["pipeline_run_id"])
        
        return {
            "morning_note": morning_note,
            "recommendations": recommendations,
            "confidence_scores": penalized_confidence_scores,
            "data_freshness": {"editor": datetime.now(UTC)},
            "flags": all_new_flags
        }

    missing_tickers: list[str] = []
    for t in tickers:
        if t not in parsed.get("recommendations", {}):
            missing_tickers.append(t)
        if t not in parsed.get("confidence_scores", {}):
            if t not in missing_tickers:
                missing_tickers.append(t)

    if missing_tickers:
        new_flags.append(
            DataFlag(
                source="editor_parse",
                severity=Severity.WARNING,
                message=f"Missing recommendations/confidence_scores for tickers: {', '.join(missing_tickers)}"
            )
        )

    recommendations: dict[str, dict] = {}
    confidence_scores: dict[str, dict[str, float]] = {}
    morning_note_sections: list[str] = []

    for t in tickers:
        if t in parsed.get("recommendations", {}) and t in parsed.get("confidence_scores", {}):
            recommendations[t] = parsed["recommendations"][t]
            confidence_scores[t] = parsed["confidence_scores"][t]
        else:
            recommendations[t] = {}
            confidence_scores[t] = {}
            morning_note_sections.append(f"### {t}\n\n[Dados indisponíveis para {t}]")

    all_new_flags = list(new_flags)

    penalized_confidence_scores, all_warnings = apply_confidence_penalties(confidence_scores, all_new_flags)

    morning_note = parsed.get("morning_note", "")
    
    if morning_note_sections:
        morning_note = "\n\n".join(morning_note_sections) + "\n\n" + morning_note
    if all_warnings:
        morning_note = "\n\n".join(all_warnings) + "\n\n" + morning_note

    confidence = state["confidence_scores"].get("editor", 1.0)
    
    await sse_service.emit_event(
        state["pipeline_run_id"],
        {
            "event_type": "agent_completed",
            "agent_name": "editor",
            "confidence_score": confidence,
            "timestamp": datetime.now(UTC).isoformat()
        }
    )
    
    await sse_service.emit_event(
        state["pipeline_run_id"],
        {
            "event_type": "note_ready",
            "morning_note_id": state["morning_note_id"],
            "timestamp": datetime.now(UTC).isoformat()
        }
    )
    
    sse_service.cleanup(state["pipeline_run_id"])

    return {
        "morning_note": morning_note,
        "recommendations": recommendations,
        "confidence_scores": penalized_confidence_scores,
        "data_freshness": {"editor": datetime.now(UTC)},
        "flags": all_new_flags
    }
