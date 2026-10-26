# Plan: Issue #110 — §4 Integration Tests (execution detail)

Parent plan: `docs/PLAN-issue-110.md`. This file is the execution plan for §4
(integration tests) plus the Option A finish: single PR, finish to plan before merge.

## Session decision that produced this plan (2026-10-02)

PR size fear → measured: 15 files, +922/−19, ~33% tests. The only clean split seam
(schema layer) is ~90 lines — splitting buys ~10%. The atomic core (interrupt +
resume) can't ship in pieces: gate without poller = every pipeline run parks forever.
**Decision: Option A — single PR, finish to plan (integration tests + ADR-029 + hygiene).**

## Findings that shape the plan (reconnaissance, 2026-10-02)

| # | Finding | Consequence |
|---|---------|-------------|
| F1 | The gate node never touches Telegram — `interrupt()` is pure (`app/agents/approval_gate.py:47-53`); the token auto-pass check lives in the poller (`app/workers/telegram_poller.py:21-26`), not the gate. The `send` node calls `build_telegram_channel()` → None with no token → FATAL flag, pipeline continues (fail-visible) | Tests 1-3 need no Telegram patching for the gate itself; send-node noise is decision D1 |
| F2 | `tests/integration/test_graph_pipeline.py:7-10` pollutes `sys.modules` globally with MagicMock for `langgraph.checkpoint.postgres(.aio)`. Real `AsyncPostgresSaver` needed. Today it works only by alphabetical collection luck (`test_approval_gate` < `test_graph_pipeline`; pytest imports all modules at collection). Renamed file or reordered collection = silent fake saver = theater test that passes | Step 0b: scope the pollution (restore originals in try/finally) |
| F3 | `handle_decision` is redis-only (`app/services/decisions.py:14-25` — SET NX dedup, no DB write). The DB write happens in the gate's resume path (`session_write_decision`, `app/agents/approval_gate.py:84-103`) | Test 2's "simulate handle_decision" = `Command(resume=...)`; the gate does the write. No redis needed unless testing replay-through-poller (D2) |
| F4 | Plan §3 drift + two latent gaps: (a) plan says "gate auto-passes on no token" but the gate always interrupts — the auto-pass INFO flag is the poller's early return; (b) poller never calls `saver.setup()` (worker does, `app/workers/pipeline.py:78`) — breaks if poller runs first on a fresh DB; (c) `telegram_update_id` column exists (UNIQUE) but nothing writes it | ADR-029 documents actual design; D3/D4 decide test 4's shape and whether the setup() fix rides this PR |

## Steps

### Step 0 — prerequisites

- 0a. `git checkout -- app/workers/telegram_poller.py` — phantom CRLF modification,
  zero content diff. **Still pending** (not run as of 2026-10-02).
- 0b. Scope `test_graph_pipeline.py`'s sys.modules pollution — restore originals in
  try/finally (F2). Otherwise the new tests can silently run against a MagicMock saver.
- 0c. `app/services/llm.py:50-51` — `logger.warning(..., exc_info=...)` in the swallowed
  except (consider same for fallback branch 35-36). Three lines. Then rerun pipeline to
  classify the editor failure (RateLimitError vs APITimeoutError vs size-dependent).
  Journal 40's first "tomorrow" item.

### Step 1 — fixture architecture (`tests/integration/test_approval_gate.py`)

- Reuse `migrated_db_url` + `bound_engine` from `tests/conftest.py` (gate's
  `SessionLocal` write lands in the container).
- Test builds its own saver: `AsyncPostgresSaver.from_conn_string(dsn)` →
  **`await saver.setup()`** (fresh container — checkpoint tables don't exist) →
  `compile_graph(saver)` — mirroring the worker's init (`app/workers/pipeline.py:72-81`),
  playing the poller's role.
- Unique `thread_id` (uuid4) per test — no cleanup needed, disposable container.
- Reuse the `patched_pipeline` mock pattern (Tavily/yfinance/summarize/editor mocked,
  editor returning valid `EDITOR_JSON`) for the agent legs.

### Step 2 — the tests

| # | Test | Asserts |
|---|------|---------|
| 1 | `test_run_to_interrupt_parks_and_persists` | `__interrupt__` in result; `aget_state().next == ("approval_gate",)`; parked checkpoint **visible from a second connection** (the assertion only real Postgres delivers); recommendation row exists with `manager_decision='pending'` (persist ran before the park) |
| 2 | `test_resume_persists_decision` | `Command(resume="approved")` → `manager_decision='approved'`, `decided_at` NOT NULL, `decision_channel='telegram'`; graph completed (`next == ()`) |
| 3 | `test_replay_is_exactly_once` | duplicate update → `handle_decision` returns None (dedup) → no resume, no second recommendation row, thread state unchanged |
| 4 | *(shape pending D3)* | no-token pipeline behavior — documents the real dev/CI path | 
| 5 | `test_ghost_resume` *(shape pending D4)* | resume-on-completed semantics / the poller guard's input contract (`snap.next == ()`, `telegram_poller.py:69-76`) |

### Step 3 — gate unit tests (also missing — plan §4 unit row)

`tests/unit/test_approval_gate.py` with `InMemorySaver`, no Docker:

- (a) no-recommendation → FATAL flag (`approval_gate.py:28-37`)
- (b) invalid decision value → FATAL flag + `decision=None` (`approval_gate.py:56-62`)
- (c) interrupt payload shape (`approval_gate.py:47-53`) — run to interrupt, assert payload fields

### Step 4 — findings follow-ups

- `telegram_update_id` dead column — write it (poller passes into resume → gate writes)
  or drop it. **ADR-029 candidate.**
- Poller missing `saver.setup()` — 1-line robustness fix. **D4 decides: ride this PR or follow-up.**
- Plan §3 "gate auto-passes" drift — ADR-029 documents the actual design (gate always
  interrupts; no-token = poller exits early with INFO flag; `run_pipeline.py` gate-parked notice).
- Pre-PR hygiene (untracked mess, scratch probes — but bank `scratch_ghost_probe.py`'s
  finding in the journal first), row-lock on gate UPDATE, f-string `SET LOCAL`. Last.

### Step 5 — verify

```bash
uv run pytest tests/unit/ tests/integration/test_approval_gate.py -v
uv run pytest tests/unit/ tests/integration/ -v   # needs Docker
uv run ruff check .
uv run mypy app
```

Commit per chunk (socratic loop), conventional messages.

## Open decisions — first item tomorrow

| # | Decision | Options | Lean |
|---|----------|---------|------|
| D1 | send-node noise in tests 1-3 | patch `app.agents.send.build_telegram_channel` with a fake channel (clean) vs accept the FATAL flag (real) | patch — FATAL noise pollutes the parked state and exactly-once assertions |
| D2 | replay test redis | hand-rolled fake redis (copy unit test's FakeRedis pattern) vs real redis via docker-compose | fake — dedup logic is unit-tested; integration tests need no redis service |
| D3 | test 4 shape | "pipeline parks at gate without token" vs drop (poller no-token INFO flag already unit-tested) | — |
| D4 | ghost test + setup fix | raw semantics (re-runs from top — documents the danger) vs guard contract (`snap.next == ()`) vs both; and does the poller `setup()` fix ride this PR | — |

## Probe evidence that shaped this plan (`scratch_ghost_probe.py`, 2026-10-02)

```
before: {} ()              ← fresh thread: nothing there
after: {} ('gate',)        ← values STILL empty, next=('gate',) — parked!
{'__interrupt__': [...]}   ← first ainvoke returned an INTERRUPT payload, not the resume value
{'value': 'approved'}      ← second ainvoke: now the resume landed
```

Resume on a thread with no checkpoint does NOT error — it silently starts a fresh run
from START, swallows the resume value, re-executes everything (persist + send + gate =
ghost recommendation row, ghost telegram send), and re-parks. Corrected the tutor's
claim ("resume fails with missing-checkpoint error"). Horn B (rollback theater — saver
commits on its own connections) still stands; InMemorySaver can't model it.
