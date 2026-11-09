# FinAgent - Current State Analysis

**Date:** November 9, 2026  
**Branch:** `main` (PR #132 merged — Issue #124 complete)  
**Latest Journal:** `docs/journal/new/1_week/48.md`

---

## Overview

FinAgent is a multi-agent AI financial analyst for Brazilian asset managers. Generates daily morning notes (in Portuguese) and structured buy/sell/keep recommendations for B3 equities at 6:00 AM BRT via Celery Beat.

**Multi-Ticker Architecture Complete**: One pipeline run per portfolio per day produces a consolidated morning note with per-ticker recommendations. LangGraph fan-out (Send API) executes Company/Quant/Risk agents in parallel per ticker, then merges via `merge_dicts` reducers. Consolidate node computes portfolio-level sector weights, concentration flags, and stale data detection.

**Target**: Asset management professionals.  
**Pricing**: To be determined (personal project).

---

## Tech Stack (Current)

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| Package Manager | `uv` (Astral) |
| Web Framework | FastAPI + Uvicorn |
| Agent Orchestration | LangGraph 1.2+ (StateGraph, Send API fan-out) |
| LLM Provider | NVIDIA NIM (OpenAI-compatible) — primary + fallback |
| Web Search | Tavily Python SDK |
| Financial Data | yfinance (Yahoo Finance) |
| ORM | SQLAlchemy 2.x (async) + Alembic |
| Database | PostgreSQL 16 (pgvector) + PostgreSQL 18 (Apache AGE) |
| Cache/Queue | Redis 7.2 (AOF) + Celery + Celery Beat |
| Observability | LangSmith (traces) + structured logging |
| Validation | Pydantic v2 + pydantic-settings |

---

## Architecture

### Multi-Ticker Agent Pipeline

```
MacroAgent (runs once) ──► Fan-out per ticker (Send API) ──► Consolidate ──► EditorAgent
                              │                    │
                              ▼                    ▼
                    CompanyAgent, QuantAgent, RiskAgent
                    (parallel per ticker)
```

- **MacroAgent**: Runs ONCE per portfolio → `macro_context: {"global": MacroOutput}`
- **Fan-out**: Company/Quant/Risk agents execute in parallel per ticker via LangGraph `Send` API
- **Consolidate Node**: Computes portfolio sector weights, concentration flags (>40%), stale data flags (>24h)
- **EditorAgent**: Loops through tickers (semaphore max 3), produces consolidated note + per-ticker recommendations + confidence scores

### AgentState (Dict-Keyed-By-Ticker with `merge_dicts` Reducers)

```python
class AgentState(TypedDict):
    # Run identifiers
    pipeline_run_id: str
    morning_note_id: str
    manager_id: int
    
    # Portfolio tickers
    company_tickers: list[str]
    
    # Per-ticker data (merged via merge_dicts)
    macro_context: Annotated[dict[str, MacroOutput], merge_dicts]              # key = "global"
    company_events: Annotated[dict[str, list[CompanyEvent]], merge_dicts]
    quant_metrics: Annotated[dict[str, QuantOutput | None], merge_dicts]
    risk_flags: Annotated[dict[str, list[RiskFlag]], merge_dicts]
    
    # Portfolio-level (from Consolidate node)
    portfolio_risk_flags: list[RiskFlag]
    portfolio_data_flags: list[DataFlag]
    sector_weights: dict[str, float]
    
    # Editor output (consolidated)
    morning_note: str | None
    recommendations: Annotated[dict[str, RecommendationPayload], merge_dicts]
    confidence_scores: Annotated[dict[str, dict[str, float]], merge_dicts]
    
    # Shared/reducer fields
    data_freshness: Annotated[dict[str, datetime], merge_dicts]
    flags: Annotated[list[DataFlag], add]
    
    # Persistence/output
    recommendation_id: int | None
    manager_decision: str | None
    decision_channel: str | None
```

---

## What's Implemented (Issues #1–#124 Complete)

### Core Infrastructure
1. **Repository & CI/CD**: GitHub Actions with unit-tests, integration-tests, standalone-graph-test jobs
2. **Docker Compose**: PG16+pgvector, PG18+AGE, Redis 7.2 with AOF
3. **Database Schema**: Alembic migrations with RLS on all tables, HNSW index, pgvector embeddings
4. **App Role Split**: `finagent_app` (NOBYPASSRLS) + dual DATABASE_URL pattern
5. **HNSW Reindex Operator**: Drift detection + `REINDEX CONCURRENTLY` script

### Multi-Ticker Pipeline (Issue #124)
6. **AgentState**: Dict-keyed-by-ticker with `merge_dicts` reducers
7. **Adapter Pattern**: `create_initial_state_multi` + deprecated `create_initial_state` wrapper
8. **Graph Restructure**: Fan-out via LangGraph `Send` API (dynamic, handles 1–50+ tickers)
9. **Consolidate Node**: Portfolio sector weights, concentration flags, stale data detection
10. **Agent Rewrites**: All agents read `current_ticker` from fan-out state; EditorAgent per-ticker loop with semaphore
11. **Standalone Test Runner**: `run_full_graph_test.py` (Windows-compatible, bypasses testcontainers)

### Agents (All 5 + Consolidate)
12. **MacroAgent**: Tavily + NIM → macro context (Selic, IPCA, FX)
13. **CompanyAgent**: Tavily + NIM → company events per ticker
14. **QuantAgent**: yfinance + NIM → P/L, EV/EBITDA, P/VPA, DY, dev_ibov (Python calculates, LLM interprets)
15. **RiskAgent**: Adversarial NIM → risk flags (probability, impact, severity)
16. **EditorAgent**: Nemotron 3 Ultra → consolidated Portuguese note + per-ticker recommendations + confidence scores
17. **Consolidate Node**: Portfolio-level sector weights, concentration flags, stale data flags

### Testing & Quality
18. **Unit Tests**: 113 passing (state, agents, parsers, flags, confidence, freshness)
19. **Integration Tests**: 49 passing (RLS, app role, graph fan-out, consolidate, reindex, agents)
20. **Standalone Full Graph Test**: 3-ticker + single-ticker modes passing
21. **Total CI**: 162 tests passing (113 unit + 49 integration) + standalone graph test green
22. **Code Quality**: ruff + mypy in CI, all clean

---

## What's Partially Implemented / In Progress (Issues #125–#129)

| Component | Issue | Status |
|-----------|-------|--------|
| **Per-Ticker Agent Rewrites** | #125 | Architecture done (fan-out + Consolidate in #124). Agents need final polish to fully use `current_ticker` consistently. |
| **Pipeline Completion Nodes** | #126 | Persist/Send/Approval/Finalize nodes exist but need integration with multi-ticker flow |
| **Worker & API: Portfolio Trigger** | #127 | Worker fetches tickers from DB; API trigger schema updated to `portfolio_id` |
| **SSE Events (Parallel)** | #128 | SSE infrastructure exists; needs per-ticker agent event emission |
| **Test Migration: Adapter Cleanup** | #129 | Adapter pattern in place; Batch 7 (cleanup) pending |

---

## What's NOT Implemented (Planned — Issues #130+)

1. **MAGMA Memory System** — 4 AGE graphs (semantic, temporal, causal, entity) + policy-guided traversal
2. **Observability** — LangSmith alerts, CloudWatch metrics/alarms, custom dashboard
3. **AWS Deploy** — RDS PG18 Multi-AZ, ElastiCache Redis, ECS services (API, Worker, Beat)
4. **Manager Onboarding** — 3 gestores, portfolio CRUD, first morning note approval
5. **Frontend** — Dashboard, Detail, SSE, Feedback (React/TS)
6. **Evals Suite** — 20 Brazilian market scenarios, baseline, regression gating
7. **Secrets Management** — AWS SSM integration
8. **Cost Tracking** — Token usage per pipeline, optimization

---

## Critical Issues (Current)

| # | Severity | Description | Location |
|---|----------|-------------|----------|
| 1 | MEDIUM | Testcontainer flakiness on Windows — standalone runner is workaround | `tests/conftest.py` |
| 2 | MEDIUM | Mock proliferation in graph tests (7 patches/test) — could use fixtures | `tests/integration/test_graph_fanout.py` |
| 3 | LOW | `consolidate_node` runtime `SessionLocal` import — minor indirection | `app/agents/consolidate.py` |

---

## Test Coverage

| Category | Files | Tests | Status |
|----------|-------|-------|--------|
| Unit | ~20 | 113 | All passing |
| Integration | ~15 | 49 | All passing |
| Standalone Graph Test | 1 | 2 modes | Passing (3-ticker + single) |
| E2E | 0 | 0 | Not implemented |
| Evals | 0 | 0 | Not implemented (Issue #130+) |
| Invariant | 3 | 3 | Freshness, RLS, Fail Visible — all blocking merge |

**CI Pipeline**: 3 jobs (unit-tests, standalone-graph-test, integration-tests) — all required on `main`.

---

## Notable Architectural Decisions (ADRs)

| ADR | Decision |
|-----|----------|
| [001](docs/adrs/001-apache-age-for-magma.md) | Apache AGE for MAGMA (single DB, ACID) |
| [002](docs/adrs/002-age-postgres-same-transaction.md) | AGE + PG in same transaction (atomic writes) |
| [003](docs/adrs/003-single-leader-replication.md) | Single-leader + read replicas |
| [004](docs/adrs/004-typed-agentstate.md) | TypedDict AgentState + Pydantic outputs |
| [005](docs/adrs/005-fail-visible.md) | Fail Visible — never silent failures |
| [006](docs/adrs/006-dual-database-url.md) | Dual DATABASE_URL (least-privilege role) |
| [007](docs/adrs/007-hnsw-reindex-drift.md) | HNSW reindex with drift detection |
| [008](docs/adrs/008-ci-integration-tests.md) | CI with PG service container |
| [009](docs/adrs/009-langgraph-reducers.md) | LangGraph reducers for parallelism |
| [010](docs/adrs/010-nvidia-nim-llm.md) | NVIDIA NIM as LLM provider |
| [031](docs/adrs/031-multi-ticker-agentstate-graph.md) | Multi-Ticker AgentState & Graph Architecture |
| [032](docs/adrs/032-multi-ticker-fanout-map.md) | Multi-Ticker Fan-Out (Send API) |
| [038](docs/adrs/038-test-migration-strategy.md) | Incremental Adapter Migration Strategy |

---

## Recommended Next Steps (from Journal 48)

1. **#125** — Agents: Per-Ticker Rewrites (core prerequisite: inject `current_ticker` via fan-out)
2. **#126** — Pipeline completion (Persist/Send/Approval/Finalize)
3. **#127** — Worker & API: Portfolio-level trigger
4. **#128** — SSE events (parallel)
5. **#129** — Test migration: Incremental adapter strategy (spans all, parallel)

---

## Git History

- **Main branch**: PR #132 merged (Issue #124 complete)
- **Active cleanup branch**: `feature/docs-cleanup` (documentation updates)
- **Pattern**: Issue-driven with PR merges into `main`; journal entries per closed issue
- **Journal**: 48 entries in `docs/journal/new/1_week/` (durable record)

---

## Summary

**FinAgent is approximately 70% complete (Issues #1–#124 of 130+ planned).** The multi-ticker architectural foundation is solid:

- ✅ Dict-keyed AgentState with `merge_dicts` reducers
- ✅ LangGraph Send API fan-out (dynamic, handles any portfolio size)
- ✅ Consolidate node for portfolio-level risk/flags
- ✅ 162 tests green in CI (unit + integration + standalone graph test)
- ✅ Adapter pattern for zero-downtime migration
- ✅ Windows-compatible standalone test runner

The largest remaining work: per-ticker agent polish (#125), pipeline completion nodes (#126), worker/API trigger (#127), SSE parallel events (#128), and MAGMA memory system (#130+).