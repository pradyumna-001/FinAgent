# FinAgent — AI Financial Analyst

> Multi-agent copilot for Brazilian asset managers. Generates daily morning notes and buy/sell/neutral recommendations for B3 equities — automatically, every day at 6:00 AM BRT.

## What It Does

FinAgent runs a pipeline of 5 specialized AI agents that work together to produce a structured morning note for each company in a manager's portfolio:

```
MacroAgent → reads macro news (Selic, inflation, FX, Fed impact on Brazil)
    ↓
CompanyAgent ←→ QuantAgent  (parallel fan-out)
    ↓               ↓
        RiskAgent  (adversarial — questions the others)
            ↓
        EditorAgent  (consolidates into morning note + recommendation)
```

**Output per company**: Morning note in Portuguese + structured recommendation (buy / sell / keep) with justification and confidence scores per section.

## Architecture Highlights

| Layer | Technology |
|-------|------------|
| **Orchestration** | LangGraph StateGraph with parallel fan-out/fan-in |
| **Memory** | MAGMA (ACL 2026) — 4 orthogonal graphs via Apache AGE |
| **Vector Search** | pgvector with HNSW index |
| **Queue** | Celery + Redis (AOF) — daily 6 AM trigger via Celery Beat |
| **API** | FastAPI with SSE for real-time pipeline updates |
| **Database** | PostgreSQL 18 (Apache AGE + pgvector) with RLS |
| **Observability** | LangSmith (traces) + CloudWatch (metrics/alarms) |
| **Security** | Row Level Security — managers cannot access each other's data |

## Key Design Decisions (ADRs)

| ADR | Decision | Summary |
|-----|----------|---------|
| [001](docs/adrs/001-apache-age-for-magma.md) | Apache AGE for MAGMA | Single DB, less infra, ACID across relational + graph |
| [002](docs/adrs/002-age-postgres-same-transaction.md) | AGE + PG in same transaction | Atomic writes: morning_note + MAGMA graphs |
| [003](docs/adrs/003-single-leader-replication.md) | Single-leader + read replicas | Write burst at 6 AM; read scaling for dashboard |
| [004](docs/adrs/004-typed-agentstate.md) | TypedDict AgentState + Pydantic outputs | Static types, reducers for parallel execution |
| [005](docs/adrs/005-fail-visible.md) | Fail Visible principle | Never silent failures; DataFlags surface gaps |
| [006](docs/adrs/006-dual-database-url.md) | Dual DATABASE_URL pattern | Least-privilege `finagent_app` role at runtime |
| [007](docs/adrs/007-hnsw-reindex-drift.md) | HNSW reindex with drift detection | Automated `REINDEX CONCURRENTLY` via operator script |
| [008](docs/adrs/008-ci-integration-tests.md) | CI with PG service container | Real DB integration tests on every push |
| [009](docs/adrs/009-langgraph-reducers.md) | LangGraph reducers for parallelism | `Annotated` merge for concurrent state updates |
| [010](docs/adrs/010-nvidia-nim-llm.md) | NVIDIA NIM as LLM provider | OpenAI-compatible, cost-effective, fallback built-in |

Full ADR documentation in [`docs/adrs/`](docs/adrs/).

## Invariants (Tested in CI)

These conditions **must always be true**. Every invariant has a corresponding integration test that blocks merge on failure.

1. **Freshness** — No metric calculated without verifying `data_freshness`. Data older than 24h triggers a `DataFlag` in the morning note.
2. **Data Isolation** — No query without `WHERE gestor_id = ?`. PostgreSQL RLS enforces this at the database level.
3. **Fail Visible** — Every data source failure generates an explicit `DataFlag`. Morning notes are never delivered without indicating what is missing.

## Project Structure

```
finAgent/
├── .github/workflows/ci.yml          # GitHub Actions CI (unit + integration)
├── alembic/                          # Database migrations
├── app/
│   ├── main.py                       # FastAPI entrypoint + lifespan
│   ├── core/                         # Config, logging, context vars
│   ├── agents/                       # 5 AI agents
│   │   ├── macro.py
│   │   ├── company.py
│   │   ├── quant.py
│   │   ├── risk.py
│   │   └── editor.py
│   ├── graph/                        # LangGraph StateGraph
│   │   ├── state.py                  # Typed AgentState, reducers, validation
│   │   └── pipeline.py               # Graph definition + checkpointers
│   ├── memory/                       # MAGMA implementation (planned)
│   ├── db/                           # SQLAlchemy models + sessions
│   ├── api/routes/                   # FastAPI routers
│   ├── services/                     # LLM, Tavily, yfinance clients
│   ├── utils/                        # DataFlag, confidence, parsers
│   └── prompts/                      # Prompt templates
├── scripts/
│   ├── init_vector.sql               # pgvector extension
│   ├── init_graph.sql                # Apache AGE extension
│   ├── reindex_hnsw.py               # HNSW drift detection + reindex
│   └── run_pipeline.py               # Terminal test script
├── tests/
│   ├── unit/                         # ~66 tests (fast, no DB)
│   ├── integration/                  # ~49 tests (real DB)
│   ├── e2e/                          # Planned
│   └── evals/                        # Planned (20 market scenarios)
├── docs/
│   ├── adrs/                         # Architecture Decision Records
│   ├── architecture.md               # Full architecture documentation
│   ├── CURRENT_STATE.md              # Current implementation status
│   ├── issues.md                     # Issue tracker (30 issues, 8 weeks)
│   └── journal/                      # Daily journal entries
├── docker-compose.yml                # Local infra (PG16+vector, PG18+AGE, Redis)
├── DEPLOYMENT.md                     # Deployment guide (local + AWS)
├── pyproject.toml
├── uv.lock
└── README.md
```

## Getting Started

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete setup instructions.

### Quick Local Setup

```bash
git clone https://github.com/pradyumna-001/FinAgent.git
cd FinAgent
uv sync --group dev
docker-compose up -d
export MIGRATION_DATABASE_URL="postgresql+psycopg://finagent:finagent_secure_pass@localhost:5432/finagent"
uv run alembic upgrade heads
export DATABASE_URL="postgresql+asyncpg://finagent:finagent_secure_pass@localhost:5432/finagent"
# Add API keys to .env or export them
uv run uvicorn app.main:app --reload
```

### Run Tests

```bash
# Unit tests (no DB)
uv run pytest tests/unit/ -v

# Integration tests (requires Docker)
docker-compose up -d postgres_vector redis
uv run pytest tests/integration/ -v

# All tests
uv run pytest -v
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check (`{status, db}`) |
| `POST` | `/pipeline/trigger` | Trigger pipeline (202 + `pipeline_run_id`) |
| `GET` | `/morning-notes` | List notes for manager (requires `manager-id` header) |
| `GET` | `/morning-notes/{id}` | Full note detail |
| `GET` | `/morning-notes/{id}/stream` | SSE real-time pipeline events |
| `POST` | `/morning-notes/{id}/feedback` | Submit manager feedback |

## Development Workflow

### Branching
- Per-issue branches: `feature/issue-XX-description`
- PR required for `main` — no direct pushes
- CI must pass (unit + integration)

### Commits
- Conventional commits: `feat(issue-XX): ...`, `fix(...): ...`, `test(...): ...`
- Socratic loop: implement → verify → commit

### Journal
- Every closed issue → journal entry in `docs/journal/new/1_week/`
- Journal is the durable record (not chat)

## Current Status

**Phase 1-2 Complete (Weeks 1-3)**: Foundation + Base Agents + Graph Pipeline
- ✅ Repository, Docker, DB schema, RLS, CI/CD
- ✅ Typed AgentState, 5 agents, LangGraph pipeline with parallel execution
- ✅ Unit + integration tests (115 total), CI green
- ✅ App role split, HNSW reindex operator, CI integration coverage

**Phase 2 Remaining**: Celery Beat, atomic writes, SSE, pipeline tests

**Phase 3+**: MAGMA memory, observability, AWS deploy, BTG onboarding, frontend

See [`docs/issues.md`](docs/issues.md) for full 30-issue, 8-week plan.

## Based On

- [MAGMA: Multi-Graph Based Agentic Memory Architecture](https://arxiv.org/abs/2601.03236) (ACL 2026)
- [Designing Data-Intensive Applications](https://dataintensive.applications) — Martin Kleppmann

## License

Proprietary — BTG Pactual internal use.