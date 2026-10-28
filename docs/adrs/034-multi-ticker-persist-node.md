# ADR-034: Multi-Ticker Persist Node — Single MorningNote UPDATE

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Pradyumna (solo)
**Related Issues**: #122 (multi-ticker morning notes), ADR-030 (schema), ADR-031 (AgentState), ADR-033 (approval)

---

## Context

Single-ticker flow: `editor → persist → send → approval_gate → finalize`
- `persist_recommendation_node`: INSERT into `recommendations` table, returns `recommendation_id`
- `send_note_node`: Uses `recommendation_id` + single ticker recommendation
- `approval_gate_node`: Interrupts with single recommendation

Multi-ticker (ADR-030 + ADR-031):
- One `MorningNote` per manager per portfolio per day
- `recommendations` JSONB: `{"PETR4": {...}, "VALE3": {...}}`
- No `Recommendation` table inserts
- `MorningNote.company_id` dropped, `portfolio_id` added

---

## Decision

### 1. Worker Creates MorningNote Before Graph Invocation

```python
# app/workers/pipeline.py - run_daily_pipeline_for_portfolio
async with SessionLocal() as session:
    await session.execute(text("SET LOCAL app.manager_id = :mid"), {"mid": manager_id})
    
    # Idempotency check: completed or generating note for today?
    existing = await session.execute(
        select(MorningNote.id).where(
            MorningNote.manager_id == manager_id,
            MorningNote.portfolio_id == portfolio_id,
            func.date(MorningNote.generated_at) == date.today(),
            MorningNote.status.in_([MorningNoteStatus.COMPLETED, MorningNoteStatus.GENERATING])
        )
    )
    if existing.scalar():
        logger.info("morning_note_exists_skip", manager_id=manager_id, portfolio_id=portfolio_id)
        return
    
    # Create MorningNote in GENERATING status
    morning_note = MorningNote(
        manager_id=manager_id,
        portfolio_id=portfolio_id,
        pipeline_run_id=pipeline_run_id,
        status=MorningNoteStatus.GENERATING,
        note_text="",  # Empty initially
        recommendations={},
        confidence_scores={},
        data_freshness={},
        flags=[],
    )
    session.add(morning_note)
    await session.flush()
    morning_note_id = morning_note.id  # Integer PK

# Invoke graph with integer morning_note_id
initial = create_initial_state(
    manager_id=manager_id,
    company_tickers=tickers,
    pipeline_run_id=pipeline_run_id,
    morning_note_id=str(morning_note_id),  # State stores as string
)
await graph.ainvoke(initial, config={"configurable": {"thread_id": pipeline_run_id}})
```

**Why worker creates**:
- Idempotency check **before** graph runs (avoids duplicate graph executions)
- `MorningNote.id` available for graph state (no round-trip)
- If graph fails, note stays `GENERATING` → visible in dashboard

### 2. Persist Node = UPDATE MorningNote (All Fields)

```python
# app/agents/persist.py
import json
from datetime import UTC, datetime
from sqlalchemy import text

from app.db.session import SessionLocal
from app.graph.state import AgentState
from app.services.sse import sse_service
from app.utils.flags import DataFlag, Severity

logger = logging.getLogger(__name__)

async def persist_recommendation_node(state: AgentState) -> dict:
    logger.info("persist_node_start", extra={"pipeline_run_id": state["pipeline_run_id"], "morning_note_id": state["morning_note_id"]})
    
    await sse_service.emit_event(state["pipeline_run_id"], {
        "event_type": "agent_started", "agent_name": "persist", "timestamp": datetime.now(UTC).isoformat()
    })
    
    new_flags = []
    
    # Validate required state
    if state["morning_note"] is None or not state["recommendations"]:
        new_flags.append(DataFlag(
            source="persist_node",
            severity=Severity.FATAL,
            message="no morning_note or recommendations in state"
        ))
        await sse_service.emit_event(state["pipeline_run_id"], {
            "event_type": "agent_completed", "agent_name": "persist", "timestamp": datetime.now(UTC).isoformat()
        })
        return {"flags": new_flags, "data_freshness": {"persist": datetime.now(UTC)}}
    
    try:
        async with SessionLocal() as session:
            await session.execute(text("SET LOCAL app.manager_id = :mid"), {"mid": state["manager_id"]})
            
            # Serialize data_freshness (datetime → ISO string)
            freshness_serializable = {}
            for k, v in state["data_freshness"].items():
                if isinstance(v, datetime):
                    freshness_serializable[k] = v.isoformat()
                else:
                    freshness_serializable[k] = v
            
            await session.execute(
                text("""
                    UPDATE morning_notes SET
                        note_text = :note_text,
                        recommendations = :recommendations,
                        confidence_scores = :confidence_scores,
                        data_freshness = :data_freshness,
                        flags = :flags,
                        status = 'completed'
                    WHERE id = :morning_note_id
                """),
                {
                    "note_text": state["morning_note"],
                    "recommendations": json.dumps(state["recommendations"]),
                    "confidence_scores": json.dumps(state["confidence_scores"]),
                    "data_freshness": json.dumps(freshness_serializable),
                    "flags": json.dumps([f.to_dict() for f in state.get("flags", [])]),
                    "morning_note_id": int(state["morning_note_id"]),
                }
            )
            await session.flush()
            
    except Exception as e:
        logger.error("persist_failed", exc_info=True)
        new_flags.append(DataFlag(
            source="persist_node",
            severity=Severity.FATAL,
            message=f"Database update failed: {e}"
        ))
        await sse_service.emit_event(state["pipeline_run_id"], {
            "event_type": "agent_completed", "agent_name": "persist", "timestamp": datetime.now(UTC).isoformat()
        })
        return {"flags": new_flags, "data_freshness": {"persist": datetime.now(UTC)}}
    
    await sse_service.emit_event(state["pipeline_run_id"], {
        "event_type": "agent_completed", "agent_name": "persist", "timestamp": datetime.now(UTC).isoformat()
    })
    
    # Return morning_note_id as recommendation_id for backward compat with send/approval_gate
    return {
        "recommendation_id": int(state["morning_note_id"]),
        "data_freshness": {"persist": datetime.now(UTC)},
        "flags": []
    }
```

### 3. Downstream Nodes Unchanged (Backward Compat)

| Node | Uses `recommendation_id` | Change |
|------|-------------------------|--------|
| `send_note_node` | Yes — builds payload | **None** — receives same `recommendation_id` (morning_note_id) |
| `approval_gate_node` | Yes — validates existence | **None** — same pattern |
| `finalize_morning_note_node` | No | **None** |

**Note**: `send_note_node` currently expects single-ticker recommendation in state. It will need update to iterate `state["recommendations"]` (see ADR-033 for approval flow, send node sends full multi-ticker message).

### 4. MorningNote Model Changes (Per ADR-030)

```python
# app/db/models.py
class MorningNote(Base):
    __tablename__ = "morning_notes"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("managers.id"), nullable=False, index=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), nullable=False, index=True)  # NEW
    # company_id: DROPPED
    pipeline_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[MorningNoteStatus] = ...
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    recommendations: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    confidence_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    data_freshness: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    flags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(HALFVEC(2048), nullable=True)
    
    # Relationships
    manager: Mapped["Manager"] = relationship(back_populates="morning_notes")
    portfolio: Mapped["Portfolio"] = relationship()
    # company: DROPPED
    # recommendation: DROPPED (was 1:1 to Recommendation table)
```

### 5. RLS Policy — Unchanged

```sql
-- morning_notes table
CREATE POLICY morning_notes_rls ON morning_notes
    USING (manager_id = current_setting('app.manager_id')::int);
-- Portfolio access controlled via manager_id on portfolios table
```

---

## Consequences

### Positive
- **Single MorningNote row** per manager/portfolio/day — matches product requirement
- **All data in one row** — note_text, recommendations, confidence, freshness, flags atomically updated
- **No Recommendation table** — simpler schema, no JOIN for recommendations
- **Idempotency at worker level** — prevents duplicate graph runs
- **Backward compat** — `recommendation_id` = `morning_note_id` keeps send/approval_gate working

### Negative / Risks
- **Worker creates row before graph** — if graph crashes, note stays `GENERATING` (visible, not lost)
- **Large JSONB** — 10 tickers × ~500 chars = ~5KB per row (acceptable for PostgreSQL JSONB)
- **UPDATE vs INSERT** — race condition if two workers create for same portfolio (mitigated by idempotency check + unique index on `(manager_id, portfolio_id, date(generated_at))`)

---

## Migration Path

1. **ADR-030 Phase 1-2**: Add `recommendations` column, `portfolio_id`, backfill
2. **Update `MorningNote` model** — drop `company_id`, `recommendation` relationship, add `portfolio_id`
3. **Update worker** — create MorningNote with `portfolio_id`, idempotency on `(manager_id, portfolio_id, date)`
4. **Rewrite `persist_recommendation_node`** — UPDATE instead of INSERT
5. **Update `send_note_node`** — iterate `state["recommendations"]` for multi-ticker message
6. **Add unique index** (ADR-030 Phase 4):
```sql
CREATE UNIQUE INDEX ux_morning_notes_manager_portfolio_date 
ON morning_notes (manager_id, portfolio_id, date(generated_at)) 
WHERE status IN ('completed', 'generating');
```

---

## Testing

| Test | Scope |
|------|-------|
| `tests/integration/test_persist_multi_ticker.py` | Persist node UPDATEs MorningNote with all fields |
| `tests/integration/test_worker_idempotency.py` | Worker skips if note exists for manager/portfolio/date |
| `tests/integration/test_send_multi_ticker.py` | Send node builds message with all tickers |
| `tests/unit/test_persist_serialization.py` | data_freshness datetime → ISO string serialization |

---

## References

- ADR-030: Multi-Ticker Database Schema
- ADR-031: Multi-Ticker AgentState & Graph
- ADR-033: Multi-Ticker Approval Gate (send node changes)
- `app/agents/persist.py` — current persist node
- `app/workers/pipeline.py` — current worker task
- `app/db/models.py` — MorningNote model