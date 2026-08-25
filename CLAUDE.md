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

**5-Agent Pipeline** (parallel fan-out/fan-in):
1. **MacroAgent** — Tavily + NIM → macro context (Selic, IPCA, FX)
2. **CompanyAgent** — Tavily + NIM → company events (earnings, dividends, M&A)
3. **QuantAgent** — yfinance + NIM → P/L, EV/EBITDA, P/VPA, DY, dev_ibov (Python calculates, LLM interprets)
4. **RiskAgent** — Adversarial NIM → risk flags (probability, impact, severity)
5. **EditorAgent** — Nemotron 3 Ultra → Portuguese morning note + recommendation + confidence scores

## Critical Invariants (Tested in CI)

1. **Freshness** — `data_freshness` verified before calculation; >24h = DataFlag
2. **RLS Isolation** — Every query requires `gestor_id`; PostgreSQL RLS enforces
3. **Fail Visible** — Every failure → DataFlag in state; EditorAgent surfaces warnings

## Key Files to Know

| File | Purpose |
|------|---------|
| `app/graph/state.py` | AgentState TypedDict, reducers, validation, create_initial_state |
| `app/graph/pipeline.py` | StateGraph with 5 nodes, validated_node wrapper, checkpointers |
| `app/agents/*.py` | 5 agent nodes — all return partial dicts, append DataFlag on failure |
| `app/utils/flags.py` | DataFlag (frozen dataclass), Severity enum (INFO/WARNING/FATAL) |
| `app/utils/editor_confidence.py` | apply_confidence_penalties — reduces scores for flagged sections |
| `app/core/logging_config.py` | Structured logging + CorrelationMiddleware (X-Pipeline-Run-Id, X-Morning-Note-Id) |
| `app/db/session.py` | Async engines, get_session (writer), get_read_session (reader) |
| `scripts/reindex_hnsw.py` | HNSW drift detection + REINDEX CONCURRENTLY operator |
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
- Unit tests: `tests/unit/` — no DB, fast (~66 tests)
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

# Celery worker
export DATABASE_URL="postgresql+asyncpg://finagent:finagent_secure_pass@localhost:5432/finagent"
export REDIS_URL="redis://localhost:6379/0"
uv run celery -A app.workers.pipeline worker --loglevel=info --concurrency=4

# Celery beat
uv run celery -A app.workers.pipeline beat --loglevel=info --scheduler=celery.beat.PersistentScheduler
```

## Current Branch State

- **Main**: Latest merged (PR #92 — Docker Compose + Celery)
- **Active**: None (all Semana 1 branches merged)
- **Next**: Issue #06 (Semana 1 review) → then #07 (Typed AgentState)

## Open Follow-ups (from journals)

1. RLS on remaining 5 tables (#03a) — managers, companies, portfolios, portfolio_holdings, recommendations
2. App role password in migration (currently set in test fixture only)
3. HNSW drift thresholds need production tuning
4. Automatic cron for reindex (script ready, needs deployment)
5. Docker layer caching for CI
6. GET /morning-notes/{id} detail endpoint (for frontend)
7. Feedback endpoint + model
8. MAGMA implementation (#16-18)
9. Celery Beat schedule persistence via volume mount (configured in #02)
10. No default secrets in docker-compose (enforced in #02)

## Agent Contract (All 5 Agents)

```python
async def agent_node(state: AgentState) -> dict:
    # 1. Log start with correlation IDs
    # 2. Try external call (Tavily, yfinance, NIM)
    # 3. On failure: append DataFlag, return partial state with None/empty output
    # 4. On success: parse/validate, return partial state with output
    # 5. ALWAYS stamp data_freshness[domain] = datetime.now(UTC)
    # 6. NEVER raise — always return dict
```

## Reducer Pattern (Parallel Agents)

```python
# In AgentState (app/graph/state.py)
data_freshness: Annotated[dict[str, datetime], merge_dicts]
flags: Annotated[list[DataFlag], add]

# Agents return partial dicts:
# company_agent → {"company_events": [...], "data_freshness": {"company": now}, "flags": [flag]}
# quant_agent   → {"quant_metrics": {...}, "data_freshness": {"quant": now}, "flags": [flag]}
# LangGraph merges via reducers automatically
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
| `docs/adrs/` | 10 Architecture Decision Records |
| `docs/issues.md` | 30-issue, 8-week plan with checkboxes |
| `docs/CURRENT_STATE.md` | Implementation status (as of 2026-07-20) |
| `docs/journal/new/1_week/` | Daily journal entries (durable record) |

## When You're Stuck

1. Check `docs/journal/new/1_week/` — latest entry has resume point
2. Check `docs/CURRENT_STATE.md` — critical issues table
3. Check `docs/adrs/` — decisions with rationale
4. Run tests to verify: `uv run pytest tests/ -v`
5. Check CI logs: GitHub Actions → failed job

---

*This file is the AI assistant context. Update when architecture decisions change.*