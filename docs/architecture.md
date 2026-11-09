# FinAgent Architecture Documentation

## System Overview

FinAgent is a multi-agent AI financial analyst that generates daily morning notes and buy/sell/neutral recommendations for Brazilian equities (B3). It runs automatically every day at 6:00 AM BRT via Celery Beat, processing all active managers and their portfolios.

**Target Users**: Asset management professionals  
**Pricing**: To be determined (personal project, not yet commercialized)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        EXTERNAL TRIGGERS                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ Celery Beat │  │  API Call   │  │  Manual     │              │
│  │ (6 AM BRT)  │  │  /trigger   │  │  Trigger    │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
└─────────┼────────────────┼────────────────┼─────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        FASTAPI API                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ POST /pipeline/trigger → 202 + pipeline_run_id          │   │
│  │ GET /morning-notes?manager_id=X → list                  │   │
│  │ GET /morning-notes/{id} → full detail                   │   │
│  │ GET /morning-notes/{id}/stream → SSE                    │   │
│  │ POST /morning-notes/{id}/feedback → update MAGMA        │   │
│  │ GET /health → {status, db}                              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CELERY WORKER POOL                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ run_daily_pipeline() task (idempotent, retryable)       │   │
│  │   → Fetches portfolio tickers from DB                   │   │
│  │   → Creates MorningNote (status=pending)                │   │
│  │   → Invokes LangGraph pipeline (multi-ticker)           │   │
│  │   → On success: status=completed, persist note+rec      │   │
│  │   → On failure: status=failed, flags in MorningNote     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LANGGRAPH STATEGRAPH (Multi-Ticker)         │
│  START                                                           │
│    │                                                             │
│    ▼                                                             │
│  MacroAgent ──────────────────────────────────────────────────┐  │
│    │                                                            │  │
│    ▼                                                            ▼  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ FAN-OUT (LangGraph Send API) — runs per ticker in parallel │  │
│  │  CompanyAgent  │  QuantAgent  │  RiskAgent                   │  │
│  │  (per ticker)  │  (per ticker)  │  (per ticker)              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│    │                                    │                          │
│    └────────────────┬───────────────────┘                          │
│                     ▼                                              │
│              Consolidate Node                                       │
│         (portfolio sector weights,                                 │
│          concentration flags,                                       │
│          stale data flags)                                         │
│                     │                                              │
│                     ▼                                              │
│              EditorAgent                                           │
│         (consolidated note +                                       │
│          per-ticker recommendations)                               │
│                     │                                              │
│                     ▼                                              │
│                    END                                             │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ PostgreSQL 16    │  │ PostgreSQL 18    │  │ Redis 7.2    │  │
│  │ (pgvector)       │  │ (Apache AGE)     │  │ (AOF)        │  │
│  │ - embeddings     │  │ - relational     │  │ - Celery     │  │
│  │ - HNSW index     │  │   schema         │  │   broker     │  │
│  │                  │  │ - MAGMA graphs   │  │ - SSE pub/sub│  │
│  └──────────────────┘  └──────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Agent Pipeline Detail

### 1. MacroAgent (`app/agents/macro.py`)
- **Input**: None (uses fixed query "macro news Brazil")
- **Tools**: Tavily API (domains: bcb.gov.br, ibge.gov.br, br.reuters.com, bloomberg.com.br)
- **LLM**: NVIDIA NIM (primary + fallback) for extraction/summary
- **Output**: `MacroOutput` (headline, summary, sources, fetched_at)
- **State updates**: `macro_context: {"global": macro_output}`, `data_freshness["macro"]`, `flags`

### 2. CompanyAgent (`app/agents/company.py`)
- **Input**: `state["current_ticker"]` (injected by fan-out) + `state["company_tickers"]`
- **Tools**: Tavily API (domains: cvm.gov.br, infomoney.com.br, globo.com/valor-economico)
- **LLM**: NVIDIA NIM for extraction
- **Output**: `list[CompanyEvent]` (title, date, source, summary)
- **State updates**: `company_events: {ticker: [...]}`, `data_freshness: {ticker: now}`, `flags`

### 3. QuantAgent (`app/agents/quant.py`)
- **Input**: `state["current_ticker"]` (injected by fan-out) + `state["company_tickers"]`
- **Tools**: yfinance (Yahoo Finance) — Python does ALL calculations
- **LLM**: NVIDIA NIM ONLY for interpretation (never calculation)
- **Critical Rule**: Verify `data_freshness` BEFORE calculation; if > 24h → `DataFlag` + no calculation
- **Calculations**: P/L, EV/EBITDA, P/VPA, dividend yield, variação vs IBOV
- **Output**: `QuantOutput` (pl, ev_ebitda, p_vpa, dividend_yield, dev_ibov, fetched_at, market_time)
- **State updates**: `quant_metrics: {ticker: QuantOutput}`, `data_freshness: {ticker: now}`, `flags`

### 4. RiskAgent (`app/agents/risk.py`)
- **Input**: `state["current_ticker"]` + reads per-ticker data from merged state:
  - `company_events = state["company_events"].get(ticker, [])`
  - `quant_metrics = state["quant_metrics"].get(ticker)`
  - `macro_context = state["macro_context"].get("global")`
- **Tools**: NONE — only analyzes upstream outputs
- **LLM**: NVIDIA NIM with adversarial prompt: *"Você é um analista cético. Encontre inconsistências, riscos ignorados e vieses"*
- **Output**: `list[RiskFlag]` (probability, impact, description, severity)
- **State updates**: `risk_flags: {ticker: [...]}`, `data_freshness: {ticker: now}`, `flags` (includes parse drops)
- **Parser**: `app/utils/risk_parse.py::parse_risk_json()` returns `(valid_flags, dropped_count)`

### 5. Consolidate Node (`app/agents/consolidate.py`) — NEW
- **Input**: Merged per-ticker state + `company_tickers` list
- **Tools**: SQLAlchemy — queries `Company.sector` for tickers
- **Computes**:
  - `sector_weights` — from portfolio holdings × company sectors
  - `portfolio_risk_flags` — sector concentration > 40%
  - `portfolio_data_flags` — stale data detection (>24h)
- **State updates**: `sector_weights`, `portfolio_risk_flags`, `portfolio_data_flags`, `data_freshness["portfolio"]`

### 6. EditorAgent (`app/agents/editor.py`)
- **Input**: Full merged state (all per-ticker dicts + portfolio fields)
- **LLM**: Nemotron 3 Ultra (single model, no fallback)
- **Prompt**: Portuguese system prompt; JSON-only response
- **Execution**: Loops through tickers with semaphore (max 3 concurrent)
- **Output structure**:
  ```json
  {
    "morning_note": "string (Portuguese, full consolidated note with per-ticker sections)",
    "recommendations": {"PETR4": {"action": "buy", "justification": "...", "confidence": 0.8}, ...},
    "confidence_scores": {"PETR4": {"macro": 0.9, "company": 0.8, "quant": 0.7, "risk": 0.6, "overall": 0.75}, ...}
  }
  ```
- **Post-processing**: `apply_confidence_penalties()` reduces scores for flagged sections (< 0.5)
- **Fail Visible**: Prepends `⚠️ Aviso: ...` warnings to morning note text
- **State updates**: `morning_note`, `recommendations`, `confidence_scores`, `data_freshness["editor"]`, `flags`

---

## State Management

### AgentState (TypedDict) — Multi-Ticker
```python
class AgentState(TypedDict):
    # Run identifiers
    pipeline_run_id: str
    morning_note_id: str
    manager_id: int
    
    # Portfolio tickers
    company_tickers: list[str]  # e.g., ["PETR4", "VALE3", "ITUB4"]
    
    # Per-ticker data — merge_dicts reducer (shallow merge by key)
    macro_context: Annotated[dict[str, MacroOutput], merge_dicts]              # key = "global"
    company_events: Annotated[dict[str, list[CompanyEvent]], merge_dicts]
    quant_metrics: Annotated[dict[str, QuantOutput | None], merge_dicts]
    risk_flags: Annotated[dict[str, list[RiskFlag]], merge_dicts]
    
    # Portfolio-level (computed by Consolidate node)
    portfolio_risk_flags: list[RiskFlag]
    portfolio_data_flags: list[DataFlag]
    sector_weights: dict[str, float]
    
    # Editor output (consolidated)
    morning_note: str | None
    recommendations: Annotated[dict[str, RecommendationPayload], merge_dicts]
    confidence_scores: Annotated[dict[str, dict[str, float]], merge_dicts]
    
    # Shared/reducer fields
    data_freshness: Annotated[dict[str, datetime], merge_dicts]  # per-ticker + "macro" + "portfolio"
    flags: Annotated[list[DataFlag], add]
    
    # Persistence/output
    recommendation_id: int | None   # Single MorningNote ID
    manager_decision: str | None
    decision_channel: str | None
```

### Reducers (for parallel execution)
- `merge_dicts(left, right)` → `{**left, **right}` (dict union) — used for all per-ticker dict fields
- `operator.add` → list concatenation for `flags`

### Validation
`InvalidStateError.validate(state)` runs before every node:
- `manager_id` is positive int (RLS invariant)
- `RiskFlag.severity` valid enum member
- `RiskFlag.probability` in [0.0, 1.0]

---

## Memory System: MAGMA (Planned)

Based on "MAGMA: Multi-Graph Based Agentic Memory Architecture" (ACL 2026, arxiv.org/abs/2601.03236)

### Four Orthogonal Graphs (Apache AGE)
| Graph | Purpose | Query Pattern |
|-------|---------|---------------|
| **Semantic** | Concept/entity relationships | Macro queries → prioritize causal + semantic |
| **Temporal** | Time-ordered event sequences | Quant queries → prioritize temporal |
| **Causal** | Cause-effect chains | Company queries → prioritize entity + temporal |
| **Entity** | Entity resolution & identity | Cross-graph entity lookup |

### Integration Points
- **EditorAgent** consults MAGMA before generating morning note
- **`update_magma_after_note()`** — updates graphs after note generated
- **`update_magma_from_feedback()`** — updates graphs with manager feedback
- **Policy-guided traversal** — rules first (no RL), then RL optimization

### Traversal Policy (Rules-Based MVP)
```
Macro query  → causal + semantic graphs
Company query → entity + temporal graphs
Quant query  → temporal graph
```

---

## Database Schema

### Core Tables (PostgreSQL 18 + AGE)
```sql
-- Managers (gestores)
managers (gestor_id PK, name, email)

-- Companies (empresas B3)
companies (empresa_id PK, ticker, nome, setor)

-- Portfolio (gestor -> empresas)
portfolios (gestor_id FK, empresa_id FK, ...)

-- Portfolio holdings (positions)
portfolio_holdings (portfolio_id FK, empresa_id FK, quantity, avg_price, ...)

-- Morning Notes (output — one per portfolio per day)
morning_notes (
  id PK,
  pipeline_run_id UUID,
  morning_note_id UUID,
  gestor_id FK,
  portfolio_id FK,
  data DATE,
  conteudo TEXT,
  confidence_scores JSONB,  -- per-ticker: {"PETR4": {...}, "VALE3": {...}}
  data_freshness JSONB,
  flags JSONB[],
  status VARCHAR -- pending|generating|completed|failed
)

-- Recommendations (structured, per-ticker)
recommendations (
  id PK,
  morning_note_id FK,
  empresa_id FK,
  acao VARCHAR, -- buy|sell|keep
  justificativa TEXT,
  confianca FLOAT
)

-- Feedback (manager input)
feedback (
  id PK,
  morning_note_id FK,
  gestor_id FK,
  acao VARCHAR,
  justificativa TEXT,
  comentario TEXT,
  created_at TIMESTAMPTZ
)
```

### Indexes
- B-tree composite: `(gestor_id, portfolio_id, data)` on morning_notes
- Partial index: `(data) WHERE status = 'completed'`
- HNSW index: `embedding` column on morning_notes (pgvector)

### Row Level Security (RLS)
All queries require `SET LOCAL app.manager_id = <gestor_id>`.
Policies enforce `gestor_id = current_setting('app.manager_id')::int`.
`finagent_app` role has `NOBYPASSRLS` — cannot bypass.

---

## Security

### Database Level
- **RLS on all tables** — No query without `gestor_id` passes
- **App role split** — `finagent_app` (runtime, DML only, NOBYPASSRLS) vs migration superuser
- **Dual DATABASE_URL** — `MIGRATION_DATABASE_URL` (DDL) vs `DATABASE_URL` (runtime)

### Application Level
- **Correlation IDs** — `X-Pipeline-Run-Id`, `X-Morning-Note-Id` headers; propagated via ContextVars
- **Structured logging** — Every log line includes `pipeline_run_id`, `morning_note_id`, `manager_id`
- **Input validation** — Pydantic schemas on all API endpoints

---

## Observability

### LangSmith (Agent Traces)
- Every pipeline run traced with tags:
  - `gestor_id:{manager_id}`
  - `portfolio_id:{portfolio_id}`
  - `tickers:["PETR4","VALE3"]`
  - `data:{YYYY-MM-DD}`
  - `pipeline_run_id:{uuid}`
  - `morning_note_id:{uuid}`
- Alerts: `confidence_score` avg < 0.70; `DataFlag` rate > 30%

### CloudWatch (Infrastructure)
- **Log Groups**: `/finagent/api`, `/finagent/celery`, `/finagent/pipeline`
- **Custom Metrics**: `pipeline_duration`, `agent_failures`, `queue_depth`, `token_cost_per_note`
- **Alarms**: pipeline_failure > 0, API error rate > 5%, Celery queue > 50, Redis memory > 80%, confidence_score < 0.70

### Structured Logging
```python
logger.info("macro_agent_start", extra={
    "pipeline_run_id": state["pipeline_run_id"],
    "morning_note_id": state["morning_note_id"],
    "manager_id": state["manager_id"]
})
```

---

## Invariants (Tested in CI)

1. **Freshness** — No metric calculated without verifying `data_freshness`. Data > 24h → `DataFlag` in morning note.
   - Test: `test_freshness_invariant` (mock yfinance with 48h data → DataFlag)

2. **Data Isolation** — No query without `WHERE gestor_id = ?`. PostgreSQL RLS enforces at DB level.
   - Test: `test_rls_isolation_invariant` (manager A accesses note B → HTTP 403)

3. **Fail Visible** — Every data source failure generates explicit flag. Morning notes never delivered without indicating gaps.
   - Test: `test_fail_visible_invariant` (mock Tavily 500 → warning in morning note)

---

## CI/CD Pipeline

### GitHub Actions (`.github/workflows/ci.yml`)
| Job | Steps | Services |
|-----|-------|----------|
| **unit-tests** | ruff, mypy, pytest tests/unit | None |
| **standalone-graph-test** | alembic upgrade heads, run_full_graph_test.py | postgres (pgvector/pgvector:pg16) |
| **integration-tests** | alembic upgrade heads, pytest tests/integration | postgres + redis |

### Branch Protection
- `main` requires: `ci/unit-tests`, `ci/standalone-graph-test`
- No direct pushes to `main` — PR required

### Test Coverage
- **Unit**: ~113 tests (freshness, confidence, DataFlag, agents, parsers, utils, multi-ticker state)
- **Integration**: ~49 tests (RLS, migration, app role, graph fan-out, consolidate, reindex, agents)
- **E2E**: Not yet implemented
- **Evals**: Not yet implemented (20 market scenarios planned)

---

## Deployment Architecture (AWS)

```
┌─────────────────────────────────────────────────────────────────┐
│                          AWS REGION                             │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   RDS PG18   │    │  ElastiCache │    │   ECS Cluster│     │
│  │  (Multi-AZ)  │    │   Redis AOF  │    │              │     │
│  │  + age, vec  │    │              │    │ ┌──────────┐ │     │
│  │  Read Replicas◄───┤              │    │ │ FastAPI  │ │     │
│  └──────────────┘    └──────────────┘    │ │ Task Def │ │     │
│        │                    ▲            │ └──────────┘ │     │
│        │                    │            │ ┌──────────┐ │     │
│        └────────────────────┘            │ │ Celery   │ │     │
│                                         │ │ Worker   │ │     │
│  ┌──────────────┐                        │ └──────────┘ │     │
│  │ Secrets Mgr  │                        │ ┌──────────┐ │     │
│  │ - API Keys   │                        │ │ Celery   │ │     │
│  │ - DB URLs    │                        │ │ Beat     │ │     │
│  └──────────────┘                        │ └──────────┘ │     │
│                                          └──────────────┘     │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐                          │
│  │  CloudWatch  │    │  LangSmith   │                          │
│  │  Logs/Met.   │    │  Traces      │                          │
│  └──────────────┘    └──────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

### ECS Services
| Service | Task Definition | Scaling |
|---------|----------------|---------|
| FastAPI | `finagent-api` | ALB target; 2–10 tasks |
| Celery Worker | `finagent-worker` | Queue depth; 1–20 tasks |
| Celery Beat | `finagent-beat` | Singleton (1 task) |

### Secrets (AWS Secrets Manager)
- `TAVILY_API_KEY`
- `NVIDIA_API_KEY`
- `LANGCHAIN_API_KEY`
- `DATABASE_URL` (finagent_app)
- `MIGRATION_DATABASE_URL` (superuser)
- `REDIS_URL`
- `SECRET_KEY`

---

## Development Workflow

### Branching
- Per-issue branches: `feature/issue-XX-description`
- No direct commits to `main`
- PR → CI green → merge (squash or merge commit)

### Commits
- Socratic loop: implement → verify → commit
- Conventional commits: `feat(issue-XX): description`, `fix(...)`, `test(...)`, `chore(...)`

### Journal
- Every closed issue → journal entry in `docs/journal/new/1_week/`
- Journal is durable record; captures decisions, resume point, mood

---

## Project Structure

```
finAgent/
├── .github/workflows/ci.yml
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI + lifespan
│   ├── core/
│   │   ├── config.py              # Pydantic Settings
│   │   ├── logging_config.py      # Structured logging + middleware
│   │   └── context.py             # ContextVars for correlation IDs
│   ├── agents/
│   │   ├── macro.py
│   │   ├── company.py
│   │   ├── quant.py
│   │   ├── risk.py
│   │   ├── editor.py
│   │   └── consolidate.py         # Portfolio-level consolidation
│   ├── graph/
│   │   ├── state.py               # AgentState, reducers, validation, create_initial_state_multi
│   │   └── pipeline.py            # StateGraph with fan-out (Send API), checkpointers
│   ├── memory/                    # MAGMA (planned)
│   │   ├── semantic.py
│   │   ├── temporal.py
│   │   ├── causal.py
│   │   ├── entity.py
│   │   └── magma.py
│   ├── db/
│   │   ├── models.py              # SQLAlchemy models
│   │   └── session.py             # Async engines + get_session
│   ├── api/
│   │   ├── routes/
│   │   │   ├── morning_notes.py
│   │   │   └── pipeline.py
│   │   ├── deps.py                # Dependencies (get_session, etc.)
│   │   └── errors.py              # Custom exceptions
│   ├── services/
│   │   ├── llm.py                 # NVIDIA NIM client
│   │   ├── tavily.py              # Tavily service
│   │   ├── yfinance.py            # yfinance service
│   │   └── pipeline.py            # Pipeline registry
│   ├── utils/
│   │   ├── flags.py               # DataFlag, Severity
│   │   ├── confidence.py          # confidence_flag()
│   │   ├── editor_confidence.py   # apply_confidence_penalties()
│   │   └── risk_parse.py          # parse_risk_json()
│   └── prompts/
│       ├── macro.py
│       ├── company.py
│       ├── quant.py
│       ├── risk.py
│       └── editor.py
├── scripts/
│   ├── init_vector.sql
│   ├── init_graph.sql
│   ├── reindex_hnsw.py
│   ├── run_pipeline.py
│   └── run_full_graph_test.py     # Standalone test runner (Windows-compatible)
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/           (planned)
│   └── evals/         (planned)
├── docs/
│   ├── adrs/
│   ├── architecture.md
│   ├── CURRENT_STATE.md
│   ├── issues.md
│   └── journal/
├── docker-compose.yml
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Next Phases

### Completed (Issues #1–#124)
- ✅ Foundation: Repository, Docker, DB schema, RLS, CI/CD
- ✅ Base Agents: Typed AgentState, 5 agents, LangGraph pipeline with parallel fan-out
- ✅ **Multi-Ticker Architecture** (Issue #124): Dict-keyed AgentState, Send API fan-out, Consolidate node
- ✅ Unit + integration tests (162 total), CI green (unit, integration, standalone graph test)
- ✅ App role split, HNSW reindex operator, CI integration coverage

### In Progress / Next (Issues #125–#129)
- **#125** — Agents: Per-Ticker Rewrites (Company/Quant/Risk/Editor read `current_ticker` from fan-out state)
- **#126** — Pipeline completion (Persist/Send/Approval/Finalize nodes)
- **#127** — Worker & API: Portfolio-level trigger (fetch tickers from DB, single graph run per portfolio)
- **#128** — SSE events (parallel per-ticker agent updates)
- **#129** — Test migration: Incremental adapter strategy (complete adapter cleanup)

### Planned (Issues #130+)
- MAGMA memory (4 AGE graphs + policy-guided traversal)
- Observability (LangSmith alerts, CloudWatch metrics/alarms)
- AWS deploy (RDS + ElastiCache + ECS)
- Manager onboarding (3 gestores)
- Frontend (Dashboard, Detail, SSE, Feedback)