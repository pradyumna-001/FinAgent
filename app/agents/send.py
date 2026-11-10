import logging
from datetime import UTC, datetime

from app.graph.state import AgentState
from app.services.channels.base import NotePayload
from app.services.channels.factory import build_telegram_channel
from app.services.sse import sse_service
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

    tickers = state.get("company_tickers", [])
    if not tickers:
        new_flags.append(DataFlag(
            source="send_node",
            severity=Severity.FATAL,
            message="no company_tickers in state"
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

    any_sent = False

    for ticker, payload in state["recommendations"].items():
        recommendation_ids = state.get("recommendation_id") or {}
        rec_id = recommendation_ids.get(ticker)
        if rec_id is None:
            new_flags.append(DataFlag(
                source="send_node",
                severity=Severity.FATAL,
                message=f"no recommendation_id for ticker {ticker} in state"
            ))
            await sse_service.emit_event(
                state["pipeline_run_id"],
                {
                    "event_type": "agent_completed",
                    "agent_name": "send",
                    "timestamp": datetime.now(UTC).isoformat()
                }
            )
            continue

        recommendation = payload
        try:
            await telegram_channel.send_note(
                NotePayload(
                    pipeline_run_id=state["pipeline_run_id"],
                    recommendation_id=rec_id,
                    ticker=ticker,
                    action=recommendation["action"],
                    confidence=recommendation["confidence"],
                    justification=recommendation["justification"]
                )
            )
            any_sent = True
        except Exception:
            new_flags.append(DataFlag(
                source="send_node",
                severity=Severity.FATAL,
                message=f"failed to send note for ticker {ticker}"
            ))
            logger.error(f"send_note_failed for ticker {ticker}", exc_info=True)

        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "agent_completed",
                "agent_name": "send",
                "timestamp": datetime.now(UTC).isoformat()
            }
        )

    decision_channel = "telegram" if any_sent else None

    return {
        "decision_channel": decision_channel,
        "flags": new_flags,
        "data_freshness": {"send": datetime.now(UTC)}
    }
