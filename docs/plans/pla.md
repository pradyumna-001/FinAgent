# Implementation Plan — Issue #110 (§4 Integration Tests)

## Status
Decisions D1-D4 answered (session 2026-10-19). Plan ready for execution.

## Decisions Applied
| # | Decision | Choice |
|---|----------|--------|
| D1 | send-node noise in tests 1-3 | Patch `build_telegram_channel` with fake channel — pure gate behavior |
| D2 | replay test redis | Real redis via docker-compose — production-faithful dedup path |
| D3 | test 4 shape | Drop — poller no-token INFO flag already unit-tested |
| D4 part 1 | test 5 shape | Both — raw semantics (ghost re-run) + guard contract (`snap.next == ()`) |
| D4 part 2 | poller `setup()` fix | Ride this PR |

## Step 0 — Prerequisites

### 0a. Revert phantom telegram_poller.py change
`git checkout -- app/workers/telegram_poller.py`
- Zero content diff, phantom CRLF modification only.
- Confirms clean working tree before new code.

### 0b. Scope `test_graph_pipeline.py` sys.modules pollution
File: `tests/integration/test_graph_pipeline.py:7-10`
- Restores original `sys.modules` entries in try/finally so new tests don't silently run against `MagicMock` savers (F2).
- Otherwise `test_approval_gate.py` could import a fake `AsyncPostgresSaver`.

### 0c. llm.py logging fix
File: `app/services/llm.py:50-51`
- Fix `logger.warning(..., exc_info=...)` in swallowed except branch; consider same for fallback branch 35-36.
- Then rerun pipeline to classify editor failure (RateLimitError vs APITimeoutError vs size-dependent).
- Journal 40 carry-over, two sessions old — do before tests.

## Step 1 — Fixture architecture (`tests/integration/test_approval_gate.py`)

- Reuse `migrated_db_url` + `bound_engine` from `tests/conftest.py` (gate's `SessionLocal` write lands in container).
- Test builds own saver: `AsyncPostgresSaver.from_conn_string(dsn)` → `await saver.setup()` → `compile_graph(saver)` — mirrors worker init (`app/workers/pipeline.py:72-81`), plays poller's role.
- Unique `thread_id` (uuid4) per test — no cleanup needed, disposable container.
- Reuse `patched_pipeline` mock pattern (Tavily/yfinance/summarize/editor mocked, editor returning valid `EDITOR_JSON`).
- **D2:** Add real redis container fixture to `tests/conftest.py` alongside Postgres testcontainer — session-scoped, fresh DB per test via unique `thread_id`.

## Step 2 — The tests (4 tests; D1, D3 applied)

| # | Test | Asserts |
|---|------|---------|
| 1 | `test_run_to_interrupt_parks_and_persists` | `__interrupt__` in result; `aget_state().next == ("approval_gate",)`; parked checkpoint **visible from second connection** (real Postgres only); recommendation row exists with `manager_decision='pending'` |
| 2 | `test_resume_persists_decision` | `Command(resume="approved")` → `manager_decision='approved'`, `decided_at` NOT NULL, `decision_channel='telegram'`; graph completed (`next == ()`) |
| 3 | `test_replay_is_exactly_once` | duplicate update → `handle_decision` returns None → no resume, no second recommendation row, thread state unchanged (**D2**: real redis) |
| 5 | `test_ghost_resume` | **Both** (**D4** part 1): raw semantics — resume on fresh thread re-executes from START, swallows resume value, re-parks; guard contract — `snap.next == ()` blocks resume, poller answers "expired or already processed" |

- **D1:** Patch `app.agents.send.build_telegram_channel` with fake channel in tests 1-3 — no FATAL `"telegram channel is unavailable"` noise in parked-state or exactly-once assertions.
- **D3:** No test 4.

## Step 3 — Gate unit tests (`tests/unit/test_approval_gate.py`)

- Uses `InMemorySaver`, no Docker.
- (a) no-recommendation → FATAL flag (`approval_gate.py:28-37`)
- (b) invalid decision value → FATAL flag + `decision=None` (`approval_gate.py:56-62`)
- (c) interrupt payload shape (`approval_gate.py:47-53`) — run to interrupt, assert payload fields

## Step 4 — Findings follow-ups

- **Poller `saver.setup()` fix rides this PR** (**D4** part 2): 1-line `await saver.setup()` after `AsyncPostgresSaver.from_conn_string(dsn)` at `telegram_poller.py:36`.
- `telegram_update_id` dead column — ADR-029 candidate: write it (poller passes into resume → gate writes) or drop it.
- ADR-029 draft — actual design: gate always interrupts; no-token = poller exits early with INFO flag; `run_pipeline.py` gate-parked notice. Documents plan §3 drift.
- Pre-PR hygiene: delete scratch probes (finding banked in journal 41), row-lock on gate UPDATE, f-string `SET LOCAL`.

## Step 5 — Verify

```bash
uv run pytest tests/unit/ tests/integration/test_approval_gate.py -v
uv run pytest tests/unit/ tests/integration/ -v   # needs Docker
uv run ruff check .
uv run mypy app
```

## Commit strategy
Commit per chunk (socratic loop), conventional messages. Single PR (Option A) — atomic core (interrupt + resume) can't ship in pieces.