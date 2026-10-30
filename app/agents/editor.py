import asyncio
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

    new_flags = []

    # Normalize flags from state (handles both DataFlag objects and dicts from reducers)
    raw_flags = state.get("flags", [])
    data_flags = []
    for f in raw_flags:
        if isinstance(f, DataFlag):
            data_flags.append(f)
        elif isinstance(f, dict) and "source" in f:
            sev = f["severity"]
            if isinstance(sev, Severity):
                severity = sev
            else:
                severity = Severity(sev)
            data_flags.append(DataFlag(
                source=f["source"],
                severity=severity,
                message=f["message"],
            ))
        else:
            logger.warning("invalid_flag_in_state", extra={"flag": f})

    tickers = state.get("company_tickers", [])

    # If no tickers, return empty but valid state
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

    # Semaphore for rate limiting concurrent LLM calls
    MAX_CONCURRENT = 3
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def process_ticker(t: str) -> tuple[str, dict | None, dict[str, float] | None, str | None, list[DataFlag]]:
        """Process a single ticker: build prompt, call LLM, parse, return structured result."""
        local_flags = []

        # Build single-ticker prompt from dict-keyed state
        user_prompt = EDITOR_PROMPTS.build_user_prompt(
            macro_context=state.get("macro_context", {}).get("global"),
            company_events=state.get("company_events", {}).get(t, []),
            quant_metrics=state.get("quant_metrics", {}).get(t),
            risk_flags=state.get("risk_flags", {}).get(t, []),
            data_flags=data_flags
        )

        async with semaphore:
            raw_text = await summarize_nemotron(
                system=EDITOR_PROMPTS.system,
                user=user_prompt
            )

        if raw_text is None:
            local_flags.append(
                DataFlag(
                    source="summarize_nemotron",
                    severity=Severity.FATAL,
                    message=f"Summarization failed for {t}"
                )
            )
            return t, None, None, None, local_flags

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            local_flags.append(
                DataFlag(
                    source="editor_parse",
                    severity=Severity.WARNING,
                    message=f"Failed to parse EditorAgent JSON response for {t}"
                )
            )
            return t, None, None, None, local_flags

        # Validate parsed response
        if not (parsed.get("morning_note") is not None and
                parsed.get("recommendation") is not None and
                parsed.get("confidence_scores") is not None):
            local_flags.append(
                DataFlag(
                    source="editor_parse",
                    severity=Severity.WARNING,
                    message=f"Missing keys in EditorAgent response for {t}"
                )
            )
            return t, None, None, None, local_flags

        is_morning_note = isinstance(parsed["morning_note"], str)
        is_recommendation = (
            isinstance(parsed["recommendation"], dict) and
            set(parsed["recommendation"].keys()) == {"action", "justification", "confidence"} and
            parsed["recommendation"]["action"] in ("buy", "sell", "keep") and
            isinstance(parsed["recommendation"]["justification"], str) and
            isinstance(parsed["recommendation"]["confidence"], float)
        )
        is_confidence_scores = (
            isinstance(parsed["confidence_scores"], dict) and
            all(isinstance(v, float) for v in parsed["confidence_scores"].values()) and
            set(parsed["confidence_scores"].keys()) == {"macro", "company", "quant", "risk", "overall"}
        )

        if not (is_morning_note and is_recommendation and is_confidence_scores):
            local_flags.append(
                DataFlag(
                    source="editor_parse",
                    severity=Severity.WARNING,
                    message=f"Invalid structure in EditorAgent response for {t}"
                )
            )
            return t, None, None, None, local_flags

        return t, parsed["recommendation"], parsed["confidence_scores"], parsed["morning_note"], local_flags

    # Process all tickers concurrently with semaphore
    results = await asyncio.gather(*[process_ticker(t) for t in tickers])

    # Aggregate results
    recommendations: dict[str, dict] = {}
    confidence_scores: dict[str, dict[str, float]] = {}
    morning_note_sections: list[str] = []
    all_new_flags = list(new_flags)  # start with flags from flag normalization

    for t, rec, conf, note_section, flags in results:
        all_new_flags.extend(flags)
        if rec is not None and conf is not None and note_section is not None:
            recommendations[t] = rec
            confidence_scores[t] = conf
            morning_note_sections.append(f"### {t}\n\n{note_section}")
        else:
            # Ticker failed - add placeholder to maintain structure
            recommendations[t] = None
            confidence_scores[t] = {}
            morning_note_sections.append(f"### {t}\n\n[Dados indisponíveis para {t}]")

    # Apply confidence penalties per ticker
    penalized_confidence_scores: dict[str, dict[str, float]] = {}
    all_warnings: list[str] = []
    for t, conf in confidence_scores.items():
        if conf:
            penalized, warnings = apply_confidence_penalties(conf, all_new_flags)
            penalized_confidence_scores[t] = penalized
            all_warnings.extend(warnings)

    # Build consolidated morning note
    morning_note = "\n\n".join(morning_note_sections)
    if all_warnings:
        morning_note = "\n\n".join(all_warnings) + "\n\n" + morning_note

    # Emit completion events (once)
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
