## Follow-up tasks after #110 merge

### 1. Drop `confirmed_at` column (low priority)
- Per ADR-029, `confirmed_at` is deprecated — `decided_at` is the authoritative timestamp
- Create migration to drop column
- Update any remaining references (should be none)

### 2. Fix idempotency gap (blocks #19)
- MorningNote status not updated to `completed` after approval
- Pipeline re-runs on same `morning_note_id` hit interrupt again
- Worker logic in #19 should update MorningNote.status = 'completed' on successful gate resume

### 3. Register `Severity`/`DataFlag` for LangGraph msgpack (medium)
- Current warning: `Deserializing unregistered type app.utils.flags.Severity from checkpoint...`
- Add to `allowed_msgpack_modules` in graph config or set `LANGGRAPH_STRICT_MSGPACK=true`
- Files: `app/graph/pipeline.py` (compile_graph) or env var

### 4. Full integration test suite stabilization (pre-existing)
- Some integration tests fail with `InterfaceError: cannot perform operation: another operation is in progress`
- Appears to be SQLAlchemy/asyncpg connection pool contention under concurrent test runs
- Unrelated to #110 changes; affects `test_sse.py`, `test_graph_pipeline.py`, `test_rls.py`

### 5. Consider explicit `SELECT FOR UPDATE NOWAIT` in gate (future)
- ADR-029 notes: if multi-worker contention appears, add explicit row lock before UPDATE
- Current: implicit lock via UPDATE in same transaction

---

**Reference**: ADR-029 (`docs/adrs/029-approval-gate.md`), PR for #110