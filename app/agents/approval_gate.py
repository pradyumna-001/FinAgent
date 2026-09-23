"""Approval gate node: pauses the graph for a human decision.

This node calls interrupt() — the body re-executes from the top on resume,
so only pure reads/guards live before the interrupt; all side effects
(DB write, SSE emit, return) live after it. Pause-time context goes to the
client via the interrupt payload; agent_completed is emitted on resume only.
"""

import logging
from datetime import UTC, datetime

from langgraph.types import interrupt
from sqlalchemy import text

from app.db.session import SessionLocal
from app.graph.state import AgentState
from app.services.sse import sse_service
from app.utils.flags import DataFlag, Severity

logger = logging.getLogger(__name__)


async def approval_gate_node(state: AgentState) -> dict:
    """Suspend until the manager approves/rejects; on resume, persist the decision."""
    recommendation_id = state.get("recommendation_id")
    recommendation = state.get("recommendation")

    if recommendation_id is None or recommendation is None:
        new_flags = [DataFlag(
            source="approval_gate_node",
            severity=Severity.FATAL,
            message="no recommendation in current state"
        )]
        return {
            "flags": new_flags,
            "data_freshness": {"approval_gate": datetime.now(UTC)}
        }

    logger.info(
        "approval_gate: awaiting decision",
        extra={
            "pipeline_run_id": state["pipeline_run_id"],
            "recommendation_id": recommendation_id,
        },
    )

    decision = interrupt({
        "recommendation_id": recommendation_id,
        "ticker": state["company_ticker"],
        "action": recommendation["action"],
        "confidence": recommendation["confidence"],
        "justification": recommendation["justification"],
    })

    new_flags = []
    if decision not in ("approved", "rejected"):
        new_flags.append(DataFlag(
            source="approval_gate_node",
            severity=Severity.FATAL,
            message=f"invalid manager decision: {decision!r}"
        ))
        decision = None

    if decision is not None:
        await session_write_decision(state, recommendation_id, decision)

    await sse_service.emit_event(
        state["pipeline_run_id"],
        {
            "event_type": "agent_completed",
            "agent_name": "approval_gate",
            "timestamp": datetime.now(UTC).isoformat()
        }
    )

    return {
        "manager_decision": decision,
        "decision_channel": "telegram" if decision is not None else None,
        "data_freshness": {"approval_gate": datetime.now(UTC)},
        "flags": new_flags,
    }


async def session_write_decision(state: AgentState, recommendation_id: int, decision: str) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL app.manager_id = '{int(state['manager_id'])}'")
            )
            await session.execute(
                text(
                    "UPDATE recommendations "
                    "SET manager_decision = :decision, "
                    "    decision_channel = 'telegram', "
                    "    decided_at = :decided_at "
                    "WHERE id = :rec_id"
                ),
                {
                    "decision": decision,
                    "decided_at": datetime.now(UTC),
                    "rec_id": recommendation_id,
                },
            )
