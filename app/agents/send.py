import logging
from datetime import datetime, UTC

from app.graph.state import AgentState
from app.services.channels.base import NotePayload
from app.services.sse import sse_service
from app.services.channels.factory import build_telegram_channel
from app.utils.flags import DataFlag, Severity


logger = logging.getLogger(__name__)

async def send_note_node(state: AgentState) -> dict:
    logger.info(
        "send_note_node_start",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "morning_note_id": state["morning_note_id"],
            "manager_id": state["manager_id"]
        }
    )

    await sse_service.emit_event(
        state["pipeline_run_id"],
        {
            "event_type": "agent_started",
            "agent_name": "send",
            "timestamp": datetime.now(UTC).isoformat()
        }
    )

    new_flags = []

    if state["recommendation_id"] is None or state["recommendation"] is None:
        new_flags.append(DataFlag(
            source="send_node",
            severity=Severity.FATAL,
            message="no recommendation in current state"
        ))

        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "agent_completed",
                "agent_name": "send",
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        return {
            "flags": new_flags,
            "data_freshness": {"send": datetime.now(UTC)}
        }

    telegram_channel = build_telegram_channel()
    if telegram_channel is None:
        new_flags.append(DataFlag(
            source="send_node",
            severity=Severity.FATAL,
            message="telegram channel is unavailable"
        ))

        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "agent_completed",
                "agent_name": "send",
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        return {
            "flags": new_flags,
            "data_freshness": {"send": datetime.now(UTC)}
        }

    payload = NotePayload(
        pipeline_run_id=state["pipeline_run_id"],
        recommendation_id=state["recommendation_id"],
        ticker=state["company_ticker"],
        action=state["recommendation"]["action"],
        confidence=state["recommendation"]["confidence"],
        justification=state["recommendation"]["justification"]
    )
    try:
        await telegram_channel.send_note(payload)

    except Exception:
        new_flags.append(DataFlag(
            source="send_node",
            severity=Severity.FATAL,
            message="telegram channel is unavailable"
            )
        )
        logger.error("send_note_failed", exc_info=True)

        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "agent_completed",
                "agent_name": "send",
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        return {
            "flags": new_flags,
            "data_freshness": {"send": datetime.now(UTC)}
        }

    await sse_service.emit_event(
        state["pipeline_run_id"],
        {
            "event_type": "agent_completed",
            "agent_name": "send",
            "timestamp": datetime.now(UTC).isoformat()
        }
    )

    return {
        "decision_channel": "telegram",
        "flags": new_flags,
        "data_freshness": {"send": datetime.now(UTC)}
    }
