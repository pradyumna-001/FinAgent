# ADR-029: Approval Gate — Decision Persistence & Human-in-the-Loop

**Status**: Accepted
**Date**: 2026-10-23
**Deciders**: Pradyumna (solo)
**Related Issues**: #110 (approval gate), #109 (channel protocol + Telegram), #111 (Sheets), #112 (Calendar)
**Supersedes**: §3 of `docs/PLAN-issue-110.md` (design drift documented here)

---

## Context

The pipeline generates a morning note with a recommendation (buy/sell/keep) for a portfolio manager (gestor). Before the note is considered "delivered," the gestor must approve or reject the recommendation. This requires:

1. **Persisting the recommendation** with a `pending` decision state
2. **Sending the note** to the gestor via a channel (Telegram initially)
3. **Pausing the pipeline** until the gestor decides
4. **Resuming** and persisting the decision (`approved`/`rejected`) with timestamp and channel
5. **Exactly-once semantics** on replay (idempotent decision handling)

The gate must be fail-visible: no exception escapes; failures append `DataFlag` and the pipeline completes.

---

## Decision

### 1. Database Schema (`recommendations` table)

Added via migration `1789584853`:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `manager_decision` | `VARCHAR(16)` | `'pending'` | `'pending' \| 'approved' \| 'rejected'` |
| `decided_at` | `TIMESTAMPTZ` | `NULL` | When gestor decision was recorded |
| `decision_channel` | `TEXT` | `NULL` | `'telegram'` (future: `'sheets'`, `'calendar'`) |
| `telegram_update_id` | `BIGINT` | `NULL` `UNIQUE` | Telegram `update_id` for idempotent replay (see §4) |

**RLS**: Inherits table-level policy (`USING (manager_id = current_setting('app.manager_id')::int)`). GRANTs for `finagent_app`: `SELECT, INSERT, UPDATE` on `recommendations`.

### 2. `confirmed_at` vs `decided_at` — One Source of Truth

| Column | Purpose | Set By |
|--------|---------|--------|
| `confirmed_at` | **Deprecated** — legacy field from earlier design | Never (keep for backward compat, do not write) |
| `decided_at` | **Authoritative** — when gestor decision persisted | `approval_gate_node` on resume |

**Rule**: `decided_at` is the only timestamp that matters for decision auditing. `confirmed_at` remains `NULL` for all new rows. Future migration may drop it.

### 3. Pipeline Architecture

```
editor → persist → send → approval_gate → END
```

- **persist**: Inserts `recommendation` row with `manager_decision='pending'`, returns `recommendation_id`
- **send**: Calls `channel.send_note(payload)` (Telegram). On failure: FATAL DataFlag, continues (fail-visible)
- **approval_gate**: 
  1. Validates `recommendation_id` + `recommendation` exist
  2. Calls `interrupt(payload)` — **always interrupts**, never auto-passes
  3. On resume: validates decision ∈ {approved, rejected}
  4. Calls `session_write_decision(state, rec_id, decision)` — writes `manager_decision`, `decided_at`, `decision_channel='telegram'`
  5. Emits SSE `agent_completed`
  6. Returns updated state

### 4. `telegram_update_id` — Written by Gate on Resume

**Decision**: Write it. The poller passes `update_id` via Redis dedup key; on resume, the gate writes it to the recommendation row.

- **Why not drop**: Enables forensic replay audit (which Telegram update triggered the decision)
- **Why not poller**: Poller is Redis-only (dedup); DB write belongs to the gate's transactional resume path
- **Uniqueness**: `UNIQUE` constraint prevents duplicate decision rows from poller retries

### 5. No-Token Behavior (Dev/CI)

**Design drift from plan §3**: The plan stated "gate auto-passes on no token." **Actual implementation**:

| Component | Behavior when `TELEGRAM_BOT_TOKEN` unset |
|-----------|------------------------------------------|
| `approval_gate` node | **Always interrupts** — pure LangGraph `interrupt()`, no token check |
| `send` node | Returns FATAL DataFlag (`telegram channel unavailable`), continues |
| `telegram_poller` | **Exits early** with INFO DataFlag: "no TELEGRAM_BOT_TOKEN — gate auto-passes" |
| `run_pipeline.py` (dev) | Detects parked state, prints notice, **manual resume via `Command(resume="approved")`** |

**Rationale**: 
- Keeps gate logic pure (no env var branching)
- Poller is the only component that knows about Telegram; it decides whether to poll
- Dev/CI workflow: pipeline parks → developer resumes manually (or CI script resumes)

### 6. Exactly-Once Replay Semantics

- **Poller dedup**: Redis `SET NX` key `decision:{run_id}:{rec_id}` (TTL 24h). Duplicate callbacks return `None`, poller answers "já registrado"
- **Gate resume guard**: Before `ainvoke(Command(resume=...))`, poller checks `snap.next == ("approval_gate",)`. If thread already completed (`next == []`), answers "decisão expirada"
- **DB uniqueness**: `telegram_update_id UNIQUE` prevents duplicate decision rows even if poller dedup fails

### 7. Row Lock on Gate UPDATE

`session_write_decision` uses `SELECT FOR UPDATE` pattern implicitly via `UPDATE ... WHERE id = :rec_id` within the same transaction that set `app.manager_id` (RLS). No explicit `FOR UPDATE` needed — the UPDATE acquires row lock.

**Note**: If future multi-worker contention appears, add `SELECT FOR UPDATE NOWAIT` on the recommendation row before UPDATE.

### 8. Parameterized `SET LOCAL`

`session_write_decision` uses f-string for `SET LOCAL app.manager_id` — **to be fixed** (security):
```python
# Current (vulnerable to injection if manager_id ever untrusted):
await session.execute(text(f"SET LOCAL app.manager_id = '{int(state['manager_id'])}'"))

# Fix (parameterized):
await session.execute(text("SET LOCAL app.manager_id = :mid"), {"mid": state["manager_id"]})
```

### 9. Poller `saver.setup()` Fix

`telegram_poller.py:36` calls `AsyncPostgresSaver.from_conn_string(dsn)` but **never calls `await saver.setup()`**. 

- **Risk**: If poller runs first on fresh DB, checkpoint tables don't exist → `ainvoke` fails
- **Fix**: Add `await saver.setup()` after context manager entry (1 line). Included in this PR.

### 10. Ghost Resume Behavior (Documented)

`scratch_ghost_probe.py` revealed: **Resume on a thread with no checkpoint does NOT error** — it silently starts a fresh run from START, swallows the resume value, re-executes all nodes (persist + send + gate = ghost recommendation row, ghost Telegram send), and re-parks.

- **Guard**: Poller checks `snap.next == ("approval_gate",)` before resume
- **Integration test**: `test_ghost_resume` asserts this behavior (expects `InvalidStateError` or no-op)

---

## Consequences

### Positive
- Clean separation: gate = pure interrupt; poller = channel-specific logic
- Fail-visible: gate never raises; DataFlags capture all failures
- Exactly-once via Redis + DB uniqueness + poller guard
- Dev/CI works without Telegram credentials

### Negative / Risks
- `confirmed_at` column dead weight (future cleanup)
- `SET LOCAL` f-string needs parameterization (low risk: `manager_id` is typed `int` from validated state)
- Poller `saver.setup()` missing (fixed in this PR)
- Plan §3 "gate auto-passes" is incorrect — documented here

---

## Testing

| Test | Scope |
|------|-------|
| `tests/unit/test_approval_gate.py` | 3 tests: no-rec, invalid-decision, interrupt payload shape (InMemorySaver) |
| `tests/integration/test_approval_gate.py` | 4 tests: run-to-interrupt, resume-persists-decision, replay-exactly-once, ghost-resume (AsyncPostgresSaver + real Postgres) |
| `tests/integration/test_app_role.py` | **Added**: verifies `finagent_app` can UPDATE new columns under RLS |

---

## Migration Path

- **New deployments**: Run `alembic upgrade head` → migration `1789584853` applies
- **Existing data**: `manager_decision` defaults to `'pending'`; `decided_at`, `decision_channel`, `telegram_update_id` are `NULL`
- **Rollback**: `alembic downgrade -1` drops the four columns

---

## Future Work

- Drop `confirmed_at` column (separate migration)
- Add `sheets_update_id`, `calendar_event_id` for multi-channel decisions
- Parameterize `SET LOCAL` in `session_write_decision`
- Consider explicit `SELECT FOR UPDATE NOWAIT` if gate contention observed

---

## References

- `docs/PLAN-issue-110.md` (original plan, §3 has drift)
- `docs/PLAN-issue-110-integration-tests.md` (execution detail, findings F1-F4, decisions D1-D4)
- `scratch_ghost_probe.py` (ghost resume evidence)
- `app/agents/approval_gate.py` (gate implementation)
- `app/workers/telegram_poller.py` (poller implementation)
- `app/services/decisions.py` (Redis dedup)
- `tests/integration/test_approval_gate.py` (integration tests)