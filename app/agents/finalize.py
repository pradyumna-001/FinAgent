"""Finalize node: marks MorningNote as completed after manager approval.

This node runs after the approval gate. It only updates the MorningNote status
to 'completed' when the manager decision is 'approved'. On 'rejected' or invalid
decision, the morning note stays in 'pending' state so it can be re-triggered.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import text

from app.db.models import MorningNoteStatus
from app.db.session import SessionLocal
from app.graph.state import AgentState
from app.services.sse import sse_service
from app.utils.flags import DataFlag, Severity

logger = logging.getLogger(__name__)


async def finalize_morning_note_node(state: AgentState) -> dict:
    """Mark MorningNote as completed after manager approval.

    Only runs when manager_decision == "approved".
    On "rejected" or None (invalid decision), returns no-op to keep note in pending.
    """
    decision = state.get("manager_decision")
    morning_note_id = state.get("morning_note_id")
    manager_id = state.get("manager_id")
    pipeline_run_id = state.get("pipeline_run_id")

    # Only finalize on approval
    if decision != "approved":
        logger.info(
            "finalize: skipping (decision not approved)",
            extra={
                "pipeline_run_id": pipeline_run_id,
                "morning_note_id": morning_note_id,
                "manager_decision": decision,
            },
        )
        return {"data_freshness": {"finalize": datetime.now(UTC)}}

    if morning_note_id is None:
        logger.warning(
            "finalize: missing morning_note_id",
            extra={"pipeline_run_id": pipeline_run_id},
        )
        return {"data_freshness": {"finalize": datetime.now(UTC)}}

    logger.info(
        "finalize: marking morning note completed",
        extra={
            "pipeline_run_id": pipeline_run_id,
            "morning_note_id": morning_note_id,
            "manager_id": manager_id,
        },
    )

    await sse_service.emit_event(
        pipeline_run_id,
        {
            "event_type": "agent_started",
            "agent_name": "finalize",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    new_flags = []

    try:
        async with SessionLocal() as session:
            async with session.begin():
                await session.execute(
                    text(f"SET LOCAL app.manager_id = {int(manager_id)}")
                )

                result = await session.execute(
                    text(
                        "UPDATE morning_notes SET status = :status WHERE id = :nid"
                    ),
                    {"status": MorningNoteStatus.COMPLETED.value, "nid": int(morning_note_id)},
                )

                # SQLAlchemy 2.0 Result has rowcount attribute
                rowcount = result.rowcount  # type: ignore[attr-defined]
                if rowcount is None or rowcount == 0:
                    logger.warning(
                        "finalize: morning note not found",
                        extra={
                            "pipeline_run_id": pipeline_run_id,
                            "morning_note_id": morning_note_id,
                        },
                    )
                    new_flags.append(DataFlag(
                        source="finalize_node",
                        severity=Severity.WARNING,
                        message=f"MorningNote {morning_note_id} not found for finalize"
                    ))

    except Exception as e:
        logger.exception(
            "finalize: database error",
            extra={
                "pipeline_run_id": pipeline_run_id,
                "morning_note_id": morning_note_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        new_flags.append(DataFlag(
            source="finalize_node",
            severity=Severity.FATAL,
            message=f"Failed to finalize morning note: {e}"
        ))

    await sse_service.emit_event(
        pipeline_run_id,
        {
            "event_type": "agent_completed",
            "agent_name": "finalize",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    return {
        "data_freshness": {"finalize": datetime.now(UTC)},
        "flags": new_flags,
    }
