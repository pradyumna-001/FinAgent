# FinAgent — AI Financial Analyst

> Multi-agent copilot for Brazilian asset managers. Generates daily morning notes and buy/sell/neutral recommendations for B3 equities — automatically, every day at 6:00 AM BRT.

## What It Does

FinAgent runs a **multi-ticker pipeline** that produces **one consolidated morning note per portfolio per day**, with per-ticker recommendations in structured JSONB:

```mermaid
flowchart TB
    %% External Triggers
    subgraph TRIGGERS["External Triggers"]
        CB[Celery Beat<br/>6:00 AM BRT<br/>Daily schedule]:::trigger
        API[API Call<br/>POST /pipeline/trigger<br/>Manual trigger]:::trigger
        MT[Manual<br/>Dashboard trigger]:::trigger
    end

    CB --> API
    API --> MT

    %% FastAPI API Layer
    subgraph API["FASTAPI API Layer"]
        direction TB
        FT[POST /pipeline/trigger<br/> 202 + pipeline_run_id]
        FM[GET /morning-notes?manager_id=X<br/> List notes]
        FD[GET /morning-notes/{id}<br/> Full note detail]
        FS[GET /morning-notes/{id}/stream<br/> SSE real-time events]
        FF[POST /morning-notes/{id}/feedback<br/> Submit manager feedback]
        FH[GET /health<br/> {status, db}]
    end

    TRIGGERS --> API

    %% Celery Worker
    subgraph CW["CELERY WORKER POOL"]
        direction TB
        WF[run_daily_pipeline() task<br/>idempotent, retryable<br/> Fetches portfolio tickers from DB<br/> Creates MorningNote (status=pending)<br/> Invokes LangGraph pipeline<br/> On success: status=completed<br/> On failure: status=failed + flags]
    end

    API --> CW

    %% LangGraph Pipeline
    subgraph LG["LANGGRAPH STATEGRAPH<br/>Multi-Ticker Pipeline"]
        direction TB
        %% Macro Agent
        MA[MacroAgent<br/> macro news<br/>Selic, inflation, FX<br/>runs ONCE per portfolio]

        %% Fan-out agents
        subgraph FO["Fan-out via Send API<br/>runs per ticker in parallel"]
            CA[CompanyAgent<br/>Tavily company events<br/>per ticker]
            QA[QuantAgent<br/>yfinance P/L, EV/EBITDA,<br/>P/VPA, dividend yield<br/>per ticker]
            RA[RiskAgent<br/>adversarial NIM <br/>risk flags per ticker]
        end

        %% Consolidate
        CN[Consolidate Node<br/>portfolio sector weights<br/>concentration flags (>40%)<br/>stale data flags (>24h)]

        %% Editor
        EA[EditorAgent<br/>Nemotron 3 Ultra<br/>consolidated Portuguese note<br/>per-ticker recommendations<br/>confidence scores]

        END1((END))

        MA --> FO
        FO --> CN
        CA --> CN
        QA --> CN
        RA --> CN
        CN --> EA
        EA --> END1
    end

    CW --> LG

    %% Data Layer
    subgraph DL["DATA LAYER"]
        direction TB
        PG[PostgreSQL 16 + pgvector<br/>+ PostgreSQL 18 + Apache AGE<br/>RLS enabled<br/>Morning notes, recommendations,<br/>companies, portfolios, holdings]
        RD[Redis 7.2 + AOF<br/>Celery broker<br/>SSE pub/sub]
    end

    LG --> DL

    %% Observability
    subgraph OBS["OBSERVABILITY"]
        CW2[CloudWatch<br/>logs + metrics + alarms]
        LS[LangSmith<br/>agent traces]
    end

    CW --> CW2
    LG --> LS

    %% Styling
    classDef trigger fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef api fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;
    classDef worker fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;
    classDef langgraph fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef datalayer fill:#fce4ec,stroke:#880e4f,stroke-width:2px;
    classDef obs fill:#f1f8e9,stroke:#33691e,stroke-width:2px;

    class CB,API,MT trigger;
    class FT,FM,FD,FS,FF,FH api;
    class WF worker;
    class MA,CA,QA,RA,CN,EA langgraph;
    class PG,RD datalayer;
    class CW2,LS obs;
```

**Output per portfolio**: Single Portuguese morning note + structured per-ticker recommendations (buy / sell / keep) with justification and confidence scores per section. Portfolio-level risk flags (sector concentration, stale data) included.

## Architecture Highlights

| Layer | Technology |
|-------|------------|
| **Orchestration** | LangGraph StateGraph with dynamic fan-out (Send API) |
| **Memory** | MAGMA (ACL 2026) — 4 orthogonal graphs via Apache AGE (planned) |
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
| [031](docs/adrs/031-multi-ticker-agentstate-graph.md) | Multi-Ticker AgentState & Graph | Dict-keyed state, fan-out, Consolidate node |
| [032](docs/adrs/032-multi-ticker-fanout-map.md) | Multi-Ticker Fan-Out | LangGraph Send API for dynamic per-ticker execution |
| [038](docs/adrs/038-test-migration-strategy.md) | Test Migration Strategy | Incremental adapter for zero-downtime migration |

Full ADR documentation in [`docs/adrs/`](docs/adrs/).

## Invariants (Tested in CI)

These conditions **must always be true**. Every invariant has a corresponding integration test that blocks merge on failure.

1. **Freshness** — No metric calculated without verifying `data_freshness`. Data older than 24h triggers a `DataFlag` in the morning note.
2. **Data Isolation** — No query without `WHERE gestor_id = ?`. PostgreSQL RLS enforces this at the database level.
3. **Fail Visible** — Every data source failure generates an explicit `DataFlag`. Morning notes are never delivered without indicating what is missing.

## Project Structure

```
finAgent/
├── .github/workflows/ci.yml          # GitHub Actions CI (unit + integration + standalone graph test)
├── alembic/                          # Database migrations
├── app/
│   ├── main.py                       # FastAPI entrypoint + lifespan
│   ├── core/                         # Config, logging, context vars
│   ├── agents/                       # 5 AI agents + Consolidate
│   │   ├── macro.py
│   │   ├── company.py
│   │   ├── quant.py
│   │   ├── risk.py
│   │   ├── editor.py
│   │   └── consolidate.py            # Portfolio-level risk/flags computation
│   ├── graph/                        # LangGraph StateGraph
│   │   ├── state.py                  # Typed AgentState, reducers, validation, create_initial_state_multi
│   │   └── pipeline.py               # Graph definition with fan-out (Send API), checkpointers
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
│   ├── run_pipeline.py               # Terminal test script
│   └── run_full_graph_test.py        # Standalone full graph test (Windows-compatible)
├── tests/
│   ├── unit/                         # ~113 tests (fast, no DB)
│   ├── integration/                  # ~49 tests (real DB)
│   ├── e2e/                          # Planned
│   └── evals/                        # Planned (20 market scenarios)
├── docs/
│   ├── adrs/                         # Architecture Decision Records (10+)
│   ├── architecture.md               # Full architecture documentation
│   ├── CURRENT_STATE.md              # Current implementation status
│   ├── issues.md                     # Issue tracker (30+ issues)
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

# Standalone full graph test (Windows-compatible, uses existing PostgreSQL)
uv run python tests/integration/run_full_graph_test.py

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

**Completed (Issues #1–#124)**:
- ✅ Foundation: Repository, Docker, DB schema, RLS, CI/CD
- ✅ Base Agents: Typed AgentState, 5 agents, LangGraph pipeline with parallel fan-out
- ✅ **Multi-Ticker Architecture** (Issue #124): Dict-keyed AgentState, Send API fan-out, Consolidate node
- ✅ Unit + integration tests (162 total), CI green (unit, integration, standalone graph test)
- ✅ App role split, HNSW reindex operator, CI integration coverage

**In Progress / Next (Issues #125–#129)**:
- **#125** — Agents: Per-Ticker Rewrites (Company/Quant/Risk/Editor read `current_ticker` from fan-out state)
- **#126** — Pipeline completion (Persist/Send/Approval/Finalize nodes)
- **#127** — Worker & API: Portfolio-level trigger (fetch tickers from DB, single graph run per portfolio)
- **#128** — SSE events (parallel per-ticker agent updates)
- **#129** — Test migration: Incremental adapter strategy (complete adapter cleanup)

**Planned (Issues #130+)**: MAGMA memory, observability, AWS deploy, manager onboarding, frontend

See [GitHub Issues](https://github.com/pradyumna-001/FinAgent/issues) for the full roadmap.

## Based On

- [MAGMA: Multi-Graph Based Agentic Memory Architecture](https://arxiv.org/abs/2601.03236) (ACL 2026)
- [Designing Data-Intensive Applications](https://dataintensive.applications) — Martin Kleppmann

## License

MIT License — Personal project by [@pradyumna-001](https://github.com/pradyumna-001). Target users: asset management professionals.