## Summary

Implements **Issue #110**: Recommendation decision schema + approval gate in pipeline.

Per `docs/PLAN-issue-110.md` and `docs/PLAN-issue-110-integration-tests.md`.

---

## Changes

### Core Implementation
- **Migration `1789584853`**: Adds `manager_decision`, `decided_at`, `decision_channel`, `telegram_update_id` to `recommendations` table
- **Pipeline wiring**: `editor → persist → send → approval_gate → END`
- **`approval_gate` node** (`app/agents/approval_gate.py`):
  - Validates recommendation exists
  - Calls `interrupt()` with payload (recommendation_id, ticker, action, confidence, justification)
  - On resume: validates decision ∈ {approved, rejected}
  - Persists decision via `session_write_decision()` with `SET LOCAL app.manager_id`
  - Returns `manager_decision`, `decision_channel`, flags
- **Poller fix** (`app/workers/telegram_poller.py:37`): Added `await saver.setup()` for fresh DB compatibility
- **`SET LOCAL` fix**: Uses f-string (PostgreSQL doesn't support parameterized `SET LOCAL`)
- **`morning_note_id` type fix** (`app/agents/persist.py`): Cast to `int` for FK insert

### Bug Fixes
- **`app/prompts/editor.py`**: Fixed indentation bug in `build_user_prompt()` — entire function body was inside `for company_events` loop, returning `None` when empty. Also fixed typo `incla` → `inclua`.

### Documentation
- **ADR-029** (`docs/adrs/029-approval-gate.md`): Documents schema, `confirmed_at` vs `decided_at`, no-token behavior (gate always interrupts; poller auto-passes), exactly-once semantics, ghost resume behavior, row lock, future work.

### Testing
- **Unit tests** (3): `test_approval_gate_node_no_recommendation`, `test_approval_gate_node_invalid_decision`, `test_approval_gate_node_valid_decision` — all passing
- **Integration tests** (4): `test_run_to_interrupt_parks_and_persists`, `test_resume_persists_decision`, `test_replay_is_exactly_once`, `test_ghost_resume` — all passing with real Postgres
- **RLS regression test**: `test_finagent_app_can_update_recommendation_decision_columns` in `test_app_role.py` — verifies `finagent_app` can UPDATE new decision columns
- **Test infrastructure fixes**:
  - `test_graph_pipeline.py`: Moved sys.modules mocks to module-scoped fixture with proper restoration (fixes F2 pollution)
  - `test_telegram_poller.py`: Added `FakeSaver.setup()` method
- **Full suite**: 98 unit tests + 12 core integration tests passing; mypy/ruff clean on `app/`

### E2E Verification
- **`scripts/verify_pipeline.py`**: Spins Docker infra, runs migrations, seeds data, compiles graph with PostgresSaver, runs full pipeline (real LLMs + Tavily + yfinance), handles approval gate interrupt, manual resume, verifies checkpoint state + DB + RLS. Passes in ~130s.

---

## Acceptance Criteria (from Issue #110)

| Criteria | Status |
|----------|--------|
| Alembic migration (4 columns) | ✅ |
| `confirmed_at` vs `decided_at` resolved in ADR-029 | ✅ |
| RLS + GRANTs for `finagent_app` + regression test | ✅ |
| AgentState extensions | ✅ |
| `approval_gate` node with interrupt | ✅ |
| Resume path (poller → handle_decision → checkpoint) | ✅ |
| No-token behavior documented | ✅ (ADR-029 §5) |
| Unit tests (mocked channel, interrupt payload) | ✅ |
| Integration tests (real Postgres, interrupt→resume, exactly-once) | ✅ |

---

## Design Decisions (from ADR-029)

| Decision | Choice |
|----------|--------|
| `telegram_update_id` column | **Write it** — gate writes on resume; enables forensic replay audit |
| No-token behavior | Gate **always interrupts**; poller exits early with INFO flag |
| Exactly-once | Redis `SET NX` + poller guard (`snap.next == ("approval_gate",)`) + DB `UNIQUE` constraint |
| Row lock | Implicit via UPDATE in same transaction; explicit `SELECT FOR UPDATE NOWAIT` if contention observed |
| `confirmed_at` | Deprecated; `decided_at` is authoritative |

---

## Follow-ups (Issue #119)

1. Drop `confirmed_at` column (low priority)
2. Fix idempotency gap — MorningNote status not updated to `completed` (blocks #19)
3. Register `Severity`/`DataFlag` for LangGraph msgpack
4. Stabilize full integration suite (pre-existing connection pool contention)
5. Consider explicit `SELECT FOR UPDATE NOWAIT` if gate contention observed

---

## How to Test

```bash
# Unit + core integration tests
pytest tests/unit/ tests/integration/test_approval_gate.py tests/integration/test_app_role.py -v

# Lint/type check
ruff check app && mypy app

# Full E2E (requires Docker + .env with API keys)
python scripts/verify_pipeline.py --no-telegram
```

---

## Commits

1. `fix(issue-110): gate resume fixes - SET LOCAL, poller setup, morning_note_id type`
2. `fix(issue-110): editor prompt indentation bug + typo (incla -> inclua)`
3. `test(issue-110): add RLS regression test; fix sys.modules pollution; FakeSaver.setup`
4. `docs(issue-110): ADR-029 approval gate; add E2E verification script`