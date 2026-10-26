# Plan: Recommendation Delivery & Approval (hackathon idea, production-grade)

Supersedes the hackathon plan (`HACKATON_PLAN.md`, `docs/hackathon/PLAN.md`) for
implementation in the real FinAgent repo. Wager (hackathon submission) is a
separate, unrelated project — nothing is ported from it.

GitHub issues: **#109–#117** (created 2026-09-14; #108 was an existing PR so
numbering shifted by one).

## Locked decisions

- **Decision storage:** extend `Recommendation` (reuse `confirmed_at`; add
  `gestor_decision`, `decided_at`). No separate decisions table.
- **Telegram transport:** long polling (dedicated poller process), behind a
  transport-agnostic seam (`handle_decision()`). Webhook route can be added
  later against the same seam.
- **Side effects (Sheets/Calendar):** only on `approve`. Best-effort; failures
  retry then surface as `DataFlag` — never block the decision.
- **Idempotency:** key = `(pipeline_run_id, recommendation_id)` everywhere;
  Telegram dedupe via stored `telegram_update_id`.
- **Approval timeout:** 30 min default (`APPROVAL_TIMEOUT_S=1800`).
- **DDIA invariants preserved:** Postgres-first writes (Ch.9), Sheets as
  best-effort replica (Ch.5), Telegram updates as inbound event stream (Ch.11),
  fail-visible DataFlags.

ADRs **#028–#031**, journal entries `docs/journal/new/1_week/32.md` onwards.

---

# Phase 1 — Feature

## Issue #109 — Channel protocol + Telegram adapter

Branch: `feature/issue-109-telegram-channel` · ADR-028 (channel adapter
protocol + long-polling choice)

New files:
- `app/services/channels/base.py` — `Channel` protocol:
  `send_note(payload)`, `await_decision(run_id, rec_id, timeout)`
- `app/services/channels/telegram_channel.py` — python-telegram-bot
  implementation; inline keyboard callback data
  `approve|reject:<pipeline_run_id>:<rec_id>`
- `app/services/decisions.py` — `handle_decision(run_id, rec_id, approved)`:
  transport-agnostic seam. Writes decision to Postgres first, then emits side
  effects (wired in #111/#112).
- `app/workers/telegram_poller.py` — long-polling loop; matches callbacks to
  pending approvals; dedupe by `telegram_update_id`; calls `handle_decision()`.

Config (`app/core/config.py` + `.env.example`):
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_POLL_TIMEOUT_S=30`,
`APPROVAL_TIMEOUT_S=1800`. Audit `.gitignore` for credential files.
Docker-compose service for the poller.

Tests (unit, no network): callback-data round-trip; `update_id` dedupe;
timeout → `None`; `handle_decision` idempotent on repeated taps. Mock
`telegram.Bot`.

---

## Issue #110 — Decision schema + approval gate in pipeline

Branch: `feature/issue-110-approval-gate` · ADR-029 (decision persistence on
`recommendations`, LangGraph interrupt design)

Migration (Alembic, superuser URL):
- `recommendations` += `gestor_decision` (`pending|approved|rejected`,
  default `pending`), `decided_at timestamptz NULL`,
  `decision_channel text NULL`, `telegram_update_id bigint NULL UNIQUE`.
- Resolve `confirmed_at` vs `decided_at` (alias or drop) — decision documented
  in ADR-029; one source of truth.
- RLS policy + GRANTs for `finagent_app`; regression via
  `tests/integration/test_app_role.py`.

Pipeline (`app/graph/pipeline.py`, `app/graph/state.py`):
- `AgentState` += `recommendation_id: str | None`, `gestor_decision: str | None`,
  `decision_channel: str | None`.
- New node `approval_gate` after `editor`: persists note+recommendation,
  `channel.send_note()`, then `interrupt()` awaiting decision. Resume: poller →
  `handle_decision()` → checkpoint resume (`thread_id = pipeline_run_id`).
- Edges: `editor → approval_gate → END`; wrapped in `validated_node`; failures
  append `DataFlag(WARNING)` and still complete (fail-visible).
- Absent `TELEGRAM_BOT_TOKEN` (dev/CI): gate auto-passes with INFO flag
  (decision documented in ADR-029).

Tests: unit (node with mocked channel; interrupt payload) + integration (run to
interrupt against real Postgres checkpointer; simulate `handle_decision`;
assert resume, persisted `gestor_decision`, exactly-once on replay).

---

## Issue #111 — Google Sheets track record (approve-only side effect)

Branch: `feature/issue-111-sheets-track-record` · ADR-030 (Sheets as
best-effort replica)

- `app/services/sheets.py` — gspread + service account. Row:
  `[timestamp, ticker, action, confidence, flags, gestor_decision, decided_at,
  latency_ms]`. Idempotent skip via `(pipeline_run_id, recommendation_id)`.
- Wired into `handle_decision()` on approve → Celery task
  `sync_decision_to_sheets` (retry w/ backoff ×5, then `DataFlag(WARNING)` on
  the morning note). Decision already durable in Postgres — Sheets never blocks.
- Config: `GOOGLE_SERVICE_ACCOUNT_JSON` (path, gitignored),
  `SHEETS_SPREADSHEET_ID`.

Tests: unit with fake gspread client (append shape, idempotent skip,
failure→retry enqueue).

---

## Issue #112 — Google Calendar events from CompanyAgent

Branch: `feature/issue-112-calendar-events` · ADR-031 (calendar idempotency,
event source)

- Surface CompanyAgent's earnings/dividends/JCP/M&A events into
  `AgentState.temporal_events` (small state extension).
- `app/services/calendar.py` — Calendar API via service account. Title
  `📊 {action}: {ticker} — {event_type}`; description links
  `GET /morning-notes/{id}`; idempotency key `f"{ticker}_{date}_{type}"` in
  extended properties; skip if exists.
- Trigger: Celery task alongside Sheets sync on approve (confirm placement in
  ADR-031). Failures → `DataFlag(WARNING)`, pipeline continues.

Tests: unit with fake Calendar client (create shape, duplicate skip,
failure→DataFlag).

---

# Phase 2 — Operability for real users (pre-deploy)

## Issue #113 — Gestor onboarding + per-manager telegram_chat_id

Branch: `feature/issue-113-gestor-onboarding`

- Migration: `managers` += `telegram_chat_id bigint NULL` (+ RLS/GRANTs audit).
- Minimal admin onboarding: script or admin endpoint to create a `Manager` row
  and capture `chat_id` (gestor messages the bot once; `getUpdates` captures
  the id — document the flow in the poller README/docs).
- Gate behavior when a manager has no `chat_id`: skip Telegram, pipeline
  completes with INFO DataFlag (same as missing-token path).
- Tests: unit + migration regression.

## Issue #114 — Secrets management

Branch: `feature/issue-114-secrets-management`

- All secrets via env-from-secret-store: `TELEGRAM_BOT_TOKEN`,
  `GOOGLE_SERVICE_ACCOUNT_JSON` path, `SECRET_KEY`, DB URLs — sourced from
  AWS SSM Parameter Store / Secrets Manager in deploy; locally via `.env`
  (gitignored).
- Document in DEPLOYMENT.md; verify no defaults in docker-compose (per #02
  rule).

## Dogfood gate (no issue — operational checklist before onboarding anyone)

- Run `scripts/run_pipeline.py` daily for 1 week on real B3 tickers with the
  author as the sole gestor (real phone, real 6 AM buzz).
- Track in a journal entry: note quality, Telegram UX (message length,
  wording, timeout behavior), DataFlag rates.
- Fix-forward issues filed from findings.

## Issue #115 — Deploy watchdog

Branch: `feature/issue-115-deploy-watchdog`

- Celery Beat job pings healthchecks.io (or equivalent dead-man's switch)
  after each successful scheduled pipeline run.
- Alert if no ping by 06:30 BRT.
- LangSmith tracing verified enabled in prod (`LANGCHAIN_TRACING_V2=true`).

---

# Phase 3 — Deployment

## Issue #116 — Minimal production deploy (EC2 + docker-compose + RDS)

Branch: `feature/issue-116-ec2-deploy`

Deliberately simple v1 (gestores < ~5), Terraform deferred:

- RDS PostgreSQL 16 + pgvector (`MIGRATION_DATABASE_URL` for migrations run
  from CI/local).
- One EC2 instance running the existing `docker-compose.yml`: FastAPI, Celery
  worker, Celery Beat, Redis, Telegram poller.
- Secrets from SSM Parameter Store; `.env` never on the repo or image.
- Backups: RDS automated snapshots; document restore in DEPLOYMENT.md.
- Smoke test: trigger pipeline in prod, receive Telegram note, approve,
  verify Sheets row.
- Update DEPLOYMENT.md with the real (tested) steps; mark the Terraform/ECS
  section as future work (#27).

## Issue #117 — Onboard first gestores (1–2)

Operational: 1–2 friendly gestores via #113 flow; feedback loop via existing
feedback endpoint; journal findings.

## Deferred

- #27–29 hardened AWS deploy (Terraform/CDK, ECS Fargate, GitHub Actions
  deploy pipeline) — revisit when gestores > ~5.
- #30 frontend.

---

# Cross-cutting quality gates (every issue)

- `uv run ruff check .` + `uv run mypy app` + relevant `pytest` suites green;
  CI must pass before merge.
- Journal entry per issue (`docs/journal/new/1_week/32.md`+).
- On #110 merge: update `CLAUDE.md` (env vars table; approval gate as 6th
  pipeline node; pruned follow-ups), `docs/architecture.md`, `README.md`.
- Cleanup after #112: remove root `HACKATON_PLAN.md`; mark `docs/hackathon/`
  docs as implemented.

# Sequencing

`#109 → #110` strictly (gate needs the channel). `#111`/`#112` independent,
parallel-safe after #110. Then `#113–#115` (operability) → dogfood gate →
`#116 → #117`.

# Open questions (resolve during ADRs)

- Calendar events per-note vs batched weekly digest (ADR-031).
- `confirmed_at` vs `decided_at` semantics (ADR-029).
