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
    new_flags = []
    tickers = state.get("company_tickers", [])
    if not tickers:
        new_flags.append(DataFlag(
            source="approval_gate_node",
            severity=Severity.FATAL,
            message="no company_tickers in state"
        ))
        return {
            "flags": new_flags,
            "data_freshness": {"approval_gate": datetime.now(UTC)}
        }

    recommendations_dict = state.get("recommendations", {})
    rec_ids = state.get("recommendation_id", {}) or {}

    if recommendations_dict == {}:
        new_flags.append(DataFlag(
            source="approval_gate_node",
            severity=Severity.FATAL,
            message="no recommendations in state"
        ))
        return {
            "flags": new_flags,
            "data_freshness": {"approval_gate": datetime.now(UTC)}
        }

    decision = interrupt({
        "recommendations": {t: rec for t, rec in recommendations_dict.items()},
        "recommendation_ids": {t: rec_ids.get(t) for t in recommendations_dict},
    })

    if decision == "approved":
        decisions = {ticker: "approved" for ticker in recommendations_dict}
    elif decision == "rejected":
        decisions = {ticker: "rejected" for ticker in recommendations_dict}
    elif isinstance(decision, dict):
        decisions = decision
    else:
        new_flags.append(DataFlag(
            source="approval_gate_node",
            severity=Severity.FATAL,
            message=f"invalid manager decision: {decision!r}"
        ))
        return {
            "flags": new_flags,
            "data_freshness": {"approval_gate": datetime.now(UTC)}
        }

    await session_write_decision(state, decisions)

    await sse_service.emit_event(
        state["pipeline_run_id"],
        {
            "event_type": "agent_completed",
            "agent_name": "approval_gate",
            "timestamp": datetime.now(UTC).isoformat()
        }
    )

    decisions_set = set(decisions.values())
    if len(decisions_set) == 1:
        manager_decision = decisions_set.pop()
    else:
        manager_decision = "partial"

    return {
        "manager_decision": manager_decision,
        "decision_channel": "telegram" if manager_decision else None,
        "data_freshness": {"approval_gate": datetime.now(UTC)},
        "flags": new_flags,
    }


async def session_write_decision(state: AgentState, decisions: dict[str, str]) -> None:
    """Persist per-ticker manager decisions to the database.

    Writes each ticker's manager_decision to its own Recommendation row
    in an independent transaction (Option B). One ticker's DB failure
    does not block others.

    Args:
        state: AgentState containing manager_id and recommendation_id
               (dict[str, int] mapping ticker to persisted row id).
        decisions: Mapping of ticker -> "approved" or "rejected".
    """
    rec_ids = state.get("recommendation_id", {}) or {}
    for ticker, decision in decisions.items():
        recommendation_id = rec_ids.get(ticker)
        if recommendation_id is None:
            logger.warning(
                "approval_gate: no recommendation_id for ticker %s in state",
                ticker,
                extra={
                    "pipeline_run_id": state["pipeline_run_id"],
                    "ticker": ticker,
                },
            )
            continue

        logger.info(
            "approval_gate: writing decision to DB",
            extra={
                "pipeline_run_id": state["pipeline_run_id"],
                "recommendation_id": recommendation_id,
                "decision": decision,
            },
        )

        async with SessionLocal() as session:
            async with session.begin():
                await session.execute(
                    text(f"SET LOCAL app.manager_id = {int(state['manager_id'])}")
                )
                await session.execute(
                    text("SELECT 1 FROM recommendations WHERE id = :rec_id FOR UPDATE NOWAIT"),
                    {"rec_id": recommendation_id},
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
