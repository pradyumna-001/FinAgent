# CLAUDE.md — FinAgent Context for AI Assistants

## Project Identity

**FinAgent** — Multi-agent AI financial analyst for Brazilian asset managers.
Generates daily morning notes + buy/sell/keep recommendations for B3 equities at 6:00 AM BRT.

*Personal project by [@pradyumna-001](https://github.com/pradyumna-001). Target users: asset management professionals.*

## Tech Stack (Current)

| Category | Technology |
|----------|------------|
| Language | Python 3.11+ |
| Package Manager | `uv` |
| Web Framework | FastAPI + Uvicorn |
| Agent Orchestration | LangGraph 1.2+ (StateGraph, parallel fan-out/fan-in) |
| LLM Provider | NVIDIA NIM (OpenAI-compatible) — primary + fallback |
| Web Search | Tavily Python SDK |
| Financial Data | yfinance (Yahoo Finance) |
| ORM | SQLAlchemy 2.x (async) + Alembic |
| Database | PostgreSQL 16 (pgvector) + PostgreSQL 18 (Apache AGE) |
| Cache/Queue | Redis 7.2 (AOF) + Celery + Celery Beat |
| Observability | LangSmith (traces) + structured logging |
| Validation | Pydantic v2 + pydantic-settings |

## Architecture Overview

```
Celery Beat (6 AM) → Celery Worker → LangGraph Pipeline → PostgreSQL + MAGMA
                                     ↓
                               FastAPI (SSE) → Frontend
```

**Multi-Ticker Pipeline** (runs once per portfolio per day):
1. **MacroAgent** — Tavily + NIM → macro context (Selic, IPCA, FX) — **runs once**
2. **Fan-out** — CompanyAgent, QuantAgent, RiskAgent run in parallel **per ticker** (LangGraph `Send` API)
3. **Consolidate Node** — Computes portfolio-level sector weights, concentration flags, stale data flags
4. **EditorAgent** — Nemotron 3 Ultra → consolidated Portuguese morning note + per-ticker recommendations + confidence scores

**AgentState** is dict-keyed-by-ticker with `merge_dicts` reducers:
- `company_tickers: list[str]` — portfolio tickers
- Per-ticker fields: `company_events`, `quant_metrics`, `risk_flags`, `recommendations`, `confidence_scores`, `data_freshness`
- Portfolio-level fields: `sector_weights`, `portfolio_risk_flags`, `portfolio_data_flags`

## Critical Invariants (Tested in CI)

1. **Freshness** — `data_freshness` verified before calculation; >24h = DataFlag
2. **RLS Isolation** — Every query requires `gestor_id`; PostgreSQL RLS enforces
3. **Fail Visible** — Every failure → DataFlag in state; EditorAgent surfaces warnings

## Key Files to Know

| File | Purpose |
|------|---------|
| `app/graph/state.py` | AgentState TypedDict, reducers, validation, create_initial_state_multi |
| `app/graph/pipeline.py` | StateGraph with fan-out (Send API), Consolidate, validated_node wrapper, checkpointers |
| `app/agents/*.py` | 5 agent nodes + consolidate — all return partial dicts, append DataFlag on failure |
| `app/agents/consolidate.py` | Consolidate node — computes portfolio sector weights, concentration flags, stale data flags |
| `app/utils/flags.py` | DataFlag (frozen dataclass), Severity enum (INFO/WARNING/FATAL) |
| `app/utils/editor_confidence.py` | apply_confidence_penalties — reduces scores for flagged sections |
| `app/core/logging_config.py` | Structured logging + CorrelationMiddleware (X-Pipeline-Run-Id, X-Morning-Note-Id) |
| `app/db/session.py` | Async engines, get_session (writer), get_read_session (reader) |
| `scripts/reindex_hnsw.py` | HNSW drift detection + REINDEX CONCURRENTLY operator |
| `scripts/run_full_graph_test.py` | Standalone full graph test runner (Windows-compatible) |
| `tests/integration/test_app_role.py` | Behavioral probes for finagent_app role permissions |

## Development Rules

### Branching
- **Per-issue branch**: `feature/issue-XX-description`
- **Never commit to main directly**
- PR → CI green → merge

### Commits
- Conventional: `feat(issue-XX): ...`, `fix(...): ...`, `test(...): ...`, `chore(...): ...`
- Socratic loop: implement chunk → verify → commit

### Journal
- Every closed issue → entry in `docs/journal/new/1_week/NN.md`
- Journal is durable record (not chat)

### Testing
- Unit tests: `tests/unit/` — no DB, fast (~113 tests)
- Integration tests: `tests/integration/` — real PostgreSQL via Docker (~49 tests)
- Run: `uv run pytest tests/unit/ -v` or `uv run pytest tests/integration/ -v`

### Code Quality
- Lint: `uv run ruff check .`
- Type check: `uv run mypy app`
- CI runs both + pytest on every push

## Environment Variables

| Variable | Used By |
|----------|---------|
| `DATABASE_URL` | App runtime (finagent_app role) |
| `MIGRATION_DATABASE_URL` | Alembic migrations (superuser) |
| `REDIS_URL` | Celery broker + SSE pub/sub |
| `TAVILY_API_KEY` | MacroAgent, CompanyAgent |
| `NVIDIA_API_KEY` | All agents (via app/services/llm.py) |
| `NVIDIA_MODEL` | Primary model (default: openai/gpt-oss-20b) |
| `NVIDIA_FALLBACK_MODEL` | Fallback model |
| `NVIDIA_NEMOTRON_MODEL` | EditorAgent only (default: nvidia/nemotron-3-ultra) |
| `LANGCHAIN_API_KEY` | LangSmith tracing |
| `LANGCHAIN_TRACING_V2` | Set "true" to enable |
| `SECRET_KEY` | FastAPI |

## Common Commands

```bash
# Install deps
uv sync --group dev

# Start local infra
docker-compose up -d

# Run migrations
export MIGRATION_DATABASE_URL="postgresql+psycopg://finagent:finagent_secure_pass@localhost:5432/finagent"
uv run alembic upgrade heads

# Start API
export DATABASE_URL="postgresql+asyncpg://finagent:finagent_secure_pass@localhost:5432/finagent"
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v

# Lint + typecheck
uv run ruff check .
uv run mypy app

# Manual pipeline test
uv run python scripts/run_pipeline.py

# HNSW reindex (dry run)
uv run python scripts/reindex_hnsw.py --dry-run

# Standalone full graph test (Windows-compatible)
uv run python tests/integration/run_full_graph_test.py

# Celery worker
export DATABASE_URL="postgresql+asyncpg://finagent:finagent_secure_pass@localhost:5432/finagent"
export REDIS_URL="redis://localhost:6379/0"
uv run celery -A app.workers.pipeline worker --loglevel=info --concurrency=4

# Celery beat
uv run celery -A app.workers.pipeline beat --loglevel=info --scheduler=celery.beat.PersistentScheduler
```

## Current Branch State

- **Main**: Latest merged (PR #132 — Issue #124 Multi-Ticker AgentState & Graph)
- **Active**: None (all Semana 1-3 branches merged)
- **Next**: Issue #125 — Agents: Per-Ticker Rewrites (Company/Quant/Risk/Editor)

## Open Follow-ups (from journals)

1. **#125** — Agents: Per-Ticker Rewrites (core prerequisite: inject `current_ticker` via fan-out)
2. **#126** — Pipeline completion (Persist/Send/Approval/Finalize)
3. **#127** — Worker & API: Portfolio-level trigger
4. **#128** — SSE events (parallel)
5. **#129** — Test migration: Incremental adapter strategy (spans all, parallel)
6. **#113** — Gestor onboarding (deferred, prerequisite for #116, #117)
7. **#114** — Secrets management (SSM)
8. **#115** — Deploy watchdog
9. **#117** — Minimal production deploy
10. **#116** — Onboard first gestores
11. **#118** — Observability & alerting
12. **#119** — Cost tracking & optimization

## Agent Contract (All 5 Agents + Consolidate)

```python
async def agent_node(state: AgentState) -> dict:
    # 1. Log start with correlation IDs
    # 2. Try external call (Tavily, yfinance, NIM)
    # 3. On failure: append DataFlag, return partial state with None/empty output
    # 4. On success: parse/validate, return partial state with output
    # 5. ALWAYS stamp data_freshness[domain] = datetime.now(UTC)
    # 6. NEVER raise — always return dict
```

**Per-ticker agents (Company, Quant, Risk)** read `state["current_ticker"]` from fan-out state:
```python
ticker = state.get("current_ticker", state["company_tickers"][0])
return {"company_events": {ticker: events}, "data_freshness": {ticker: now}, "flags": new_flags}
```

**MacroAgent** runs once, outputs to `macro_context["global"]` key.

**EditorAgent** loops through all tickers with semaphore (max 3 concurrent), produces:
- `morning_note`: consolidated string with per-ticker sections
- `recommendations`: `dict[ticker, RecommendationPayload]`
- `confidence_scores`: `dict[ticker, dict[section, float]]`

## Reducer Pattern (Parallel Agents)

```python
# In AgentState (app/graph/state.py)
company_events: Annotated[dict[str, list[CompanyEvent]], merge_dicts]
quant_metrics: Annotated[dict[str, QuantOutput | None], merge_dicts]
risk_flags: Annotated[dict[str, list[RiskFlag]], merge_dicts]
recommendations: Annotated[dict[str, RecommendationPayload], merge_dicts]
confidence_scores: Annotated[dict[str, dict[str, float]], merge_dicts]
data_freshness: Annotated[dict[str, datetime], merge_dicts]
flags: Annotated[list[DataFlag], add]

# Per-ticker agents return dict-keyed output:
# company_agent → {"company_events": {"PETR4": [...]}, "data_freshness": {"PETR4": now}, "flags": [flag]}
# quant_agent   → {"quant_metrics": {"PETR4": {...}}, "data_freshness": {"PETR4": now}, "flags": [flag]}
# LangGraph merges via reducers automatically across fan-out iterations
```

## RLS Pattern

```python
# In API endpoint (app/api/routes/morning_notes.py)
async with session.begin():
    await session.execute(text(f"SET LOCAL app.manager_id = '{manager_id}'"))
    # All subsequent queries in this transaction filtered by RLS
```

## MAGMA (Planned)

Based on ACL 2026 paper. Four AGE graphs:
- `magma_semantic` — concept relationships
- `magma_temporal` — event sequences
- `magma_causal` — cause-effect chains
- `magma_entity` — entity resolution

Integration: EditorAgent consults before generation; `update_magma_after_note()` + `update_magma_from_feedback()` after.

## Documentation Map

| Document | Purpose |
|----------|---------|
| `README.md` | Project overview, quick start |
| `DEPLOYMENT.md` | Local + AWS deployment guide |
| `docs/architecture.md` | Full architecture documentation |
| `docs/adrs/` | 10+ Architecture Decision Records |
| `docs/issues.md` | 30-issue, 8-week plan with checkboxes |
| `docs/CURRENT_STATE.md` | Implementation status (updated 2026-11) |
| `docs/journal/new/1_week/` | Daily journal entries (durable record) |

## When You're Stuck

1. Check `docs/journal/new/1_week/` — latest entry has resume point
2. Check `docs/CURRENT_STATE.md` — critical issues table
3. Check `docs/adrs/` — decisions with rationale
4. Run tests to verify: `uv run pytest tests/ -v`
5. Check CI logs: GitHub Actions → failed job

---

*This file is the AI assistant context. Update when architecture decisions change.*