# FinAgent - Current State Analysis

**Date:** July 20, 2026
**Branch:** `feature/graph-pipeline` (13 commits ahead of merge base)

---

## Overview

FinAgent is a multi-agent AI financial analyst designed as a copilot for Brazilian asset managers. It generates daily morning notes (in Portuguese) and structured buy/sell/hold recommendations for companies listed on B3 (Brazilian stock exchange). The system is intended to run automatically every day at 6AM via Celery Beat.

**Target:** Asset management professionals.
**Pricing:** To be determined (personal project).

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.14 |
| Package Manager | `uv` (Astral) |
| Web Framework | FastAPI + Uvicorn |
| Agent Orchestration | LangGraph (StateGraph with parallel fan-out/fan-in) |
| LLM Provider | DeepSeek API (via OpenAI-compatible SDK) |
| Web Search | Tavily Python SDK |
| Financial Data | yfinance (Yahoo Finance) |
| ORM | SQLAlchemy 2.x (async) + Alembic migrations |
| Database | PostgreSQL 16 (pgvector for embeddings) + PostgreSQL 18 (Apache AGE for graphs) |
| Cache/Queue | Redis 7.2 (AOF persistence) |
| Task Queue | Celery + Celery Beat |
| Observability | LangSmith (agent traces) + structured logging |
| Validation | Pydantic v2 + pydantic-settings |

---

## Architecture

### Agent Pipeline

```
START --> macro_agent --> company_agent --\
                                          +--> risk_agent --> editor_agent --> END
                       macro_agent --> quant_agent ---/
```

- `company_agent` and `quant_agent` execute **in parallel** (fan-out after `macro_agent`)
- `risk_agent` waits for **both** to complete (fan-in)

### The Five AI Agents

| Agent | File | Input | Purpose |
|-------|------|-------|---------|
| **MacroAgent** | `app/agents/macro.py` | Tavily search + DeepSeek | Macro analysis (GDP, IPCA, Selic) in Portuguese |
| **CompanyAgent** | `app/agents/company.py` | Tavily search + DeepSeek | Corporate events (dividends, earnings, M&A) |
| **QuantAgent** | `app/agents/quant.py` | yfinance + DeepSeek | Financial metrics (PE, EV/EBITDA, dividend yield) |
| **RiskAgent** | `app/agents/risk.py` | All upstream outputs + DeepSeek | Adversarial auditor -- questions assumptions |
| **EditorAgent** | `app/agents/editor.py` | All upstream outputs + DeepSeek | Compiles final morning note + recommendation |

---

## Directory Structure

```
finAgent/
  .github/workflows/ci.yml        # GitHub Actions CI
  docs/                            # Documentation
  README.md                        # Project README
  DEPLOYMENT.md                    # Deployment guide (local + AWS)
  finagent/                        # Main application package
    pyproject.toml
    docker-compose.yml             # postgres_vector, postgres_graph, redis
    alembic.ini
    app/
      main.py                      # FastAPI entrypoint
      core/
        config.py                  # Pydantic Settings
        logging_config.py          # Structured tracing + middleware
      agents/                      # 5 AI agent implementations
      graph/
        state.py                   # AgentState + Pydantic schemas + reducers
        builder.py                 # LangGraph DAG assembly
        pipeline.py                # Pipeline runner with checkpointing
      api/routes.py                # APIRouter (stub /analyze endpoint)
      db/
        models.py                  # 5 SQLAlchemy ORM models
        session.py                 # Async engine + RLS context
      schemas/analysis.py          # Request/Response Pydantic models
      services/analysis.py         # Skeleton AnalysisService
      utils/data_preprocessing.py  # DataFlag, freshness checks
      prompts/                     # 9 prompt template files + loader service
      clients/                     # Empty placeholder
    alembic/versions/              # Initial schema migration
    scripts/                       # SQL init scripts
    tests/
      unit/                        # 8 unit test files (~37 tests)
      integration/                 # 2 integration test files (~5 tests)
    agents_scripts/                # Manual live testing scripts
```

---

## What's Implemented

1. All 5 agent nodes with Tavily/DeepSeek/yfinance integrations
2. LangGraph StateGraph with parallel fan-out/fan-in topology
3. Typed AgentState with reducers, validators, and Pydantic output schemas
4. Prompt management service with 9 template files and validation
5. Database schema with Alembic migration, pgvector embedding column, RLS policies
6. Docker Compose with separated PostgreSQL containers + Redis
7. FastAPI application with health check, pipeline trigger stub, and morning notes endpoint
8. Structured logging with correlation ID propagation
9. Live agent scripts for manual testing
10. CI pipeline via GitHub Actions

---

## What's Partially Implemented (Stubs)

| Component | Status |
|-----------|--------|
| `POST /pipeline/trigger` | Returns UUID but does NOT dispatch Celery task |
| `GET /analyze/{ticker}` | Returns hardcoded skeleton response |
| `AnalysisService` | Accepts `None` for all clients, returns static message |
| `app/clients/` | Empty placeholder directory |
| `GET /morning-notes` | Raw SQL `SELECT *` without ORM, no per-manager filtering |

---

## What's NOT Implemented (Planned)

1. **MAGMA memory system** -- no `app/memory/` directory; semantic/temporal/causal/entity graph implementations absent
2. **Celery tasks** -- no `app/workers/` directory; no worker or beat config
3. **SSE streaming** -- no `GET /morning-notes/{id}/stream` endpoint
4. **Feedback endpoint** -- no `POST /recommendations/{id}/feedback`
5. **E2E tests** -- no `tests/e2e/` directory
6. **Eval suite** -- no `tests/evals/` directory
7. **Invariant integration tests** -- referenced in CLAUDE.md but do not exist
8. **AWS deployment** -- no IaC (Terraform/CDK) files
9. **Apache AGE graph operations** -- container exists but no code writes/queries AGE graphs
10. **Morning note persistence** -- pipeline produces notes but never writes them to PostgreSQL
11. **Manager CRUD API** -- no endpoint for adding/querying managers or portfolios

---

## Critical Issues

| # | Severity | Description | Location |
|---|----------|-------------|----------|
| 1 | CRITICAL | API key mismatch: agent code reads `DEEPSEEK_API_KEY` but docs/tests reference `OPENROUTER_API_KEY` | All agent files |
| 2 | HIGH | Pipeline does not persist results to PostgreSQL -- DB schema (MorningNote, Recommendation) is unused | `graph/pipeline.py` |
| 3 | HIGH | Pipeline trigger is a stub -- returns UUID but doesn't invoke pipeline | `app/main.py:42-49` |
| 4 | HIGH | Company agent `base_url` contains markdown link syntax causing connection error | `app/agents/company.py:90` |
| 5 | MEDIUM | Prompt loader directory resolution is fragile -- will cause `FileNotFoundError` | `app/prompts/services/prompt_loader.py:14-18` |
| 6 | MEDIUM | Editor test asserts fields not set by agent code | `tests/unit/test_editor.py:87-88` |
| 7 | MEDIUM | Quant test expects stale data flag not generated by agent | `tests/unit/test_quant.py:61-68` |
| 8 | MEDIUM | Prompt variable names mismatch between quant agent code and template | `app/agents/quant.py:50`, `app/prompts/quant_agent_user.txt` |
| 9 | MEDIUM | Python version mismatch: `pyproject.toml` requires 3.14, CI uses 3.11 | `pyproject.toml:6`, `ci.yml:24` |
| 10 | LOW | `logging_config.py` copy-paste bug: sets `pipeline_run_id_ctx` instead of `morning_note_id_ctx` | `app/core/logging_config.py:43` |

---

## Test Coverage

| Category | Files | Tests | Status |
|----------|-------|-------|--------|
| Unit | 8 | ~37 | Good coverage, but 5+ tests would fail at runtime |
| Integration | 2 | ~5 | Covers pipeline checkpointing and agent failures |
| E2E | 0 | 0 | Not implemented |
| Eval | 0 | 0 | Not implemented |
| Invariant | 0 | 0 | Referenced but not implemented |
| Config | 1 | 1 | Minimal |
| API endpoints | 0 | 0 | No tests for FastAPI routes |

**CI:** GitHub Actions runs `pytest tests/` on push/PR to `main`. No linting (ruff) or type checking (mypy) steps despite being dev dependencies.

---

## Notable Architectural Decisions

1. **Fail Visible Principle** -- Every agent catches exceptions and appends `DataFlag` objects. The editor agent includes explicit hazard banners in sections with data gaps.
2. **Delta-Based State Updates** -- Agents return only modified fields. Custom reducers (`merge_lists`, `merge_dicts`) enable safe parallel execution.
3. **Validation Wrapper** -- Every graph node is decorated with `_wrap_with_validation()` for early corruption detection.
4. **Dual-Database Architecture** -- PostgreSQL 16 (pgvector) and PostgreSQL 18 (Apache AGE) isolated in separate containers to avoid C-API incompatibilities.
5. **Correlation ID Tracking** -- Every log line includes `pipeline_run_id` and `morning_note_id`.

---

## Recommended Next Steps

1. Fix the DeepSeek vs OpenRouter API key mismatch across agents, tests, and documentation
2. Fix the company agent `base_url` markdown syntax bug
3. Fix the prompt loader directory resolution
4. Implement morning note persistence to PostgreSQL after pipeline completion
5. Wire the pipeline trigger endpoint to Celery task dispatch
6. Fix failing test assertions to bring test suite to passing
7. Build the MAGMA memory system (largest remaining technical component)
8. Add Celery worker + Beat configuration
9. Create invariant integration tests
10. Add ruff and mypy to CI pipeline

---

## Git History

- **28 total local branches** (many feature branches from issue-based development)
- **Recent focus:** Implementing agent nodes, LangGraph topology, prompt management, and integration tests
- **Pattern:** Issue-driven with PR merges into `main`

---

## Summary

**FinAgent is approximately 30-35% complete (Week 2-3 of an 8-week plan).** The core multi-agent pipeline is functionally implemented with all 5 agents operational, a typed state machine, parallel graph execution, and a solid test foundation. The code quality is generally high with consistent patterns around error handling, typed schemas, and structured logging.

The largest gaps are: (1) no persistence of pipeline results to the database, (2) no Celery task queue integration, (3) no MAGMA memory system, and (4) multiple runtime bugs that need fixing before the system can run end-to-end.
