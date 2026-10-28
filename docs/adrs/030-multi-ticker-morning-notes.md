# ADR-030: Multi-Ticker Morning Notes — Database Schema & Migration Strategy

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Pradyumna (solo)
**Related Issues**: #122 (multi-ticker morning notes), #119 (follow-ups), #19 (idempotent pipeline)

---

## Context

Currently, the pipeline generates **one `MorningNote` per manager per ticker per day**:
- `MorningNote.company_id` FK → single ticker
- `MorningNote.recommendation` relationship → 1:1 to `Recommendation` table
- Idempotency key: `(manager_id, company_id, date)`

**Issue #122** requires: **one morning note per manager per day, covering all tickers in their portfolio**, with per-ticker recommendations stored in a single JSONB column.

**Target schema**:
- `MorningNote.company_id` → **dropped**
- `MorningNote.recommendations` JSONB → `{"PETR4": {"action": "buy", ...}, "VALE3": {...}}`
- `Recommendation` table → **dropped** (data migrated to JSONB)
- Idempotency key: `(manager_id, date)` with `company_id IS NULL` filter
- Unique index to prevent duplicate multi-ticker notes

---

## Decision

### 1. Schema Changes (`MorningNote`)

| Column | Before | After |
|--------|--------|-------|
| `company_id` | `FK companies.id`, `NOT NULL`, indexed | **Dropped** |
| `recommendation` (relationship) | 1:1 to `Recommendation` table | **Dropped** (ORM only) |
| `recommendations` | — | `JSONB`, `NOT NULL`, default `'{}'` — keyed by ticker |

**New `recommendations` JSONB structure**:
```json
{
  "PETR4": {
    "action": "buy",
    "confidence": 0.82,
    "justification": "Strong fundamentals...",
    "manager_decision": "pending",
    "decided_at": null,
    "decision_channel": null
  },
  "VALE3": {
    "action": "keep",
    "confidence": 0.65,
    "justification": "Mixed signals...",
    "manager_decision": "pending",
    "decided_at": null,
    "decision_channel": null
  }
}
```

### 2. `Recommendation` Table — Drop with Backward-Compat View

**Drop the table entirely** (no dual-write, no soft deprecation). Rationale:
- No production data exists in `recommendations` yet (Issue #119 follow-up 119.1 dropped `confirmed_at`, confirming table is not in active use)
- JSONB column is the authoritative store going forward
- Simpler migration: no dual-write logic, no sync bugs

**Backward-compatibility view** for any legacy queries/tests:
```sql
CREATE VIEW recommendations AS
SELECT
    r.id,
    r.morning_note_id,
    r.ticker,
    r.data->>'action' AS action,
    (r.data->>'confidence')::float AS confidence,
    r.data->>'justification' AS justification,
    r.mn_created_at AS created_at,
    r.data->>'manager_decision' AS manager_decision,
    (r.data->>'decided_at')::timestamptz AS decided_at,
    r.data->>'decision_channel' AS decision_channel,
    NULL::bigint AS telegram_update_id
FROM (
    SELECT
        mn.id AS morning_note_id,
        mn.generated_at AS mn_created_at,
        jsonb_each(mn.recommendations) AS kv
    FROM morning_notes mn
    WHERE mn.recommendations != '{}'
) mn_rec,
LATERAL (
    SELECT
        row_number() OVER () AS id,
        mn_rec.morning_note_id,
        mn_rec.kv.key AS ticker,
        mn_rec.kv.value AS data,
        mn_rec.mn_created_at
) r;
```

**RLS probes** updated to query `MorningNote.recommendations` JSONB directly (not the view, since ORM mapping to view is fragile).

### 3. Three-Phase Migration (Sequential, Back-to-Back)

| Phase | Migration | Operations | Code Compatibility |
|-------|-----------|------------|---------------------|
| **1** | Additive | `ADD COLUMN recommendations JSONB DEFAULT '{}'` | Old code ignores new column |
| **2** | Data Backfill | `UPDATE morning_notes SET recommendations = ... FROM recommendations r JOIN companies c ... WHERE mn.company_id IS NOT NULL` | Old code still works |
| **3** | **Deploy new code** | — | New code reads/writes `recommendations` JSONB |
| **4** | Cutover | `DROP COLUMN company_id`, `DROP TABLE recommendations`, `CREATE VIEW recommendations`, `CREATE UNIQUE INDEX ux_morning_notes_manager_date_new ON morning_notes (manager_id, date(generated_at)) WHERE company_id IS NULL AND status = 'completed'` | New code only |

**Critical**: Phases 1–2 must complete **before** Phase 3 (deploy). Phase 4 runs immediately after deploy in same pipeline.

### 4. Idempotency Logic Update

**New `should_skip_manager` logic** (deployed with Phase 3):
```python
async def should_skip_manager(manager_id: int, date: date) -> bool:
    async with SessionLocal() as session:
        # Primary: check new-format multi-ticker note
        result = await session.execute(
            select(MorningNote.id).where(
                MorningNote.manager_id == manager_id,
                func.date(MorningNote.generated_at) == date,
                MorningNote.status == "completed",
                MorningNote.company_id.is_(None)
            )
        )
        if result.scalar():
            return True
        
        # Fallback: old single-ticker notes exist but no new note → allow run to consolidate
        result = await session.execute(
            select(func.count(MorningNote.id)).where(
                MorningNote.manager_id == manager_id,
                func.date(MorningNote.generated_at) == date,
                MorningNote.status == "completed",
                MorningNote.company_id.is_not(None)
            )
        )
        return False  # Run pipeline to create consolidated note
```

**Unique index** (Phase 4) is the hard safety net:
```sql
CREATE UNIQUE INDEX ux_morning_notes_manager_date_new 
ON morning_notes (manager_id, date(generated_at)) 
WHERE company_id IS NULL AND status = 'completed';
```

### 5. RLS Policy — Unchanged

`MorningNote.manager_id` remains. Existing policy `USING (manager_id = current_setting('app.manager_id')::int)` continues to work. No RLS changes needed.

---

## Consequences

### Positive
- Single note per manager per day matches product requirement
- JSONB enables flexible per-ticker payload evolution (add fields without migrations)
- Dropping `Recommendation` table simplifies schema — no JOIN needed for recommendations
- Unique index provides database-level idempotency guarantee (race-condition proof)

### Negative / Risks
- JSONB queries less ergonomic than relational (mitigated by view for legacy access)
- Migration requires careful sequencing (Phase 1→2→deploy→4)
- Existing single-ticker notes become "orphans" after Phase 4 (acceptable — historical, read-only)
- `Recommendation` ORM model removed — any remaining references must be updated

---

## Testing

| Test | Scope |
|------|-------|
| `tests/integration/test_migration_030.py` | Migration phases 1–4 apply cleanly; data backfill correct |
| `tests/integration/test_rls_probes.py` | Updated probe queries `MorningNote.recommendations` JSONB |
| `tests/unit/test_idempotency.py` | `should_skip_manager` handles old/new formats correctly |
| `tests/integration/test_unique_index.py` | Duplicate insert raises `IntegrityError` |

---

## Migration Path

- **New deployments**: `alembic upgrade head` applies all 4 migrations sequentially
- **Existing data**: Phase 2 backfills `recommendations` JSONB from `Recommendation` + `Company` tables
- **Rollback**: 
  - Before Phase 3: `alembic downgrade -2` (drops `recommendations` column)
  - After Phase 3: Not trivial — requires recreating `Recommendation` table and splitting JSONB. Documented as "do not rollback after deploy."

---

## Future Work

- Add `telegram_update_id` per ticker in JSONB if per-ticker approval needed
- Consider GIN index on `recommendations` for ticker lookup performance
- Archive old single-ticker notes to separate table after cutover

---

## References

- `docs/issues.md` — Issue #122 spec
- `docs/journal/new/1_week/45.md` — Resume point mentioning #122
- `app/db/models.py` — Current `MorningNote` and `Recommendation` models
- `app/graph/state.py` — `AgentState` changes tracked in ADR-031 (next)