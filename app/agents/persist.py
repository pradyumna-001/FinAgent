import logging
from datetime import UTC, datetime

from sqlalchemy import text

from app.db.models import Recommendation
from app.db.session import SessionLocal
from app.graph.state import AgentState
from app.services.sse import sse_service
from app.utils.flags import DataFlag, Severity

logger = logging.getLogger(__name__)


async def persist_recommendation_node(state: AgentState) -> dict:
    logger.info(
        "persist_recommendation_node_start",
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
            "agent_name": "persist",
            "timestamp": datetime.now(UTC).isoformat()
        }
    )

    new_flags = []

    tickers = state.get("company_tickers", [])
    if not tickers:
        new_flags.append(DataFlag(
            source="persist_node",
            severity=Severity.FATAL,
            message="no company_tickers in state"
        ))
        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "agent_completed",
                "agent_name": "persist",
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        return {
            "flags": new_flags,
            "data_freshness": {"persist": datetime.now(UTC)}
        }

    ticker = tickers[0]
    recommendation = state.get("recommendations", {}).get(ticker)

    if recommendation is None:
        new_flags.append(DataFlag(
            source="persist_node",
            severity=Severity.FATAL,
            message=f"no recommendation for ticker {ticker} in current state"
        ))

        await sse_service.emit_event(
            state["pipeline_run_id"],
            {
                "event_type": "agent_completed",
                "agent_name": "persist",
                "timestamp": datetime.now(UTC).isoformat()
            }
        )
        return {
            "flags": new_flags,
            "data_freshness": {"persist": datetime.now(UTC)}
        }

    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL app.manager_id = '{int(state['manager_id'])}'")
            )

            recommendation_obj = Recommendation(
                morning_note_id=int(state["morning_note_id"]),
                action=recommendation["action"],
                confidence=recommendation["confidence"],
                justification=recommendation["justification"],
            )

            session.add(recommendation_obj)
            await session.flush()
            rec_id = recommendation_obj.id

    confidence = state["confidence_scores"].get("persist", 1.0)
    await sse_service.emit_event(
        state["pipeline_run_id"],
        {
            "event_type": "agent_completed",
            "agent_name": "persist",
            "confidence_score": confidence,
            "timestamp": datetime.now(UTC).isoformat()
        }
    )

    return {
        "recommendation_id": rec_id,
        "decision_channel": None,
        "data_freshness": {"persist": datetime.now(UTC)},
        "flags": []
    }
