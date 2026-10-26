# Plan: Issue #110 — Decision Schema + Approval Gate in Pipeline

## Sequencing
- `#109 → #110` strictly (gate needs the channel from #109)
- `#111`/`#112` independent, parallel-safe after #110

## 1. Migration (Alembic, superuser URL)
- `recommendations` += `gestor_decision` (`pending|approved|rejected`, default `pending`), `decided_at timestamptz NULL`, `decision_channel text NULL`, `telegram_update_id bigint NULL UNIQUE`
- Resolve `confirmed_at` vs `decided_at` (alias or drop) — one source of truth; documented in ADR-029
- RLS policy + GRANTs for `finagent_app`; regression via `tests/integration/test_app_role.py`

## 2. AgentState Extensions (`app/graph/state.py`)
- `AgentState` += `recommendation_id: str | None`, `gestor_decision: str | None`, `decision_channel: str | None`

## 3. New Pipeline Node: `approval_gate` (`app/graph/pipeline.py`)
- Placed after `editor` node
- Persists note + recommendation
- Calls `channel.send_note()`, then `interrupt()` awaiting decision
- Resume: poller → `handle_decision()` → checkpoint resume (`thread_id = pipeline_run_id`)
- Wrapped in `validated_node`; failures append `DataFlag(WARNING)` and still complete (fail-visible)
- Absent `TELEGRAM_BOT_TOKEN` (dev/CI): gate auto-passes with INFO flag (decision documented in ADR-029)

## 4. Tests
- **Unit**: node with mocked channel; interrupt payload
- **Integration**: run to interrupt against real Postgres checkpointer; simulate `handle_decision`; assert resume, persisted `gestor_decision`, exactly-once on replay

## 5. Post-merge updates (per cross-cutting quality gates)
- Update `CLAUDE.md` (env vars table; approval gate as 6th pipeline node; pruned follow-ups)
- Update `docs/architecture.md`, `README.md`

## Cross-cutting quality gates (every issue)
- `uv run ruff check .` + `uv run mypy app` + relevant `pytest` suites green; CI must pass before merge
- Journal entry per issue (`docs/journal/new/1_week/32.md`+)