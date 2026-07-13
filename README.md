# FinAgent — AI Financial Analyst

> Multi-agent copilot for Brazilian asset managers. Generates daily morning notes and buy/sell recommendations for B3 equities — automatically, every day at 6AM.

## What it does

FinAgent runs a pipeline of 5 specialized AI agents that work together to produce a structured morning note for each company in a manager's portfolio:

```
MacroAgent → reads macro news (Selic, inflation, FX, Fed impact on Brazil)
    ↓
CompanyAgent ←→ QuantAgent  (parallel)
    ↓               ↓
        RiskAgent  (adversarial — questions the others)
            ↓
        EditorAgent  (consolidates into morning note + recommendation)
```

**Output per company:** morning note in Portuguese + structured recommendation (buy / sell / neutral) with justification and confidence scores.

## Architecture

- **Orchestration:** LangGraph StateGraph with parallel execution
- **Memory:** MAGMA (ACL 2026) — 4 orthogonal graphs (semantic, temporal, causal, entity) via Apache AGE
- **Vector search:** pgvector with HNSW index for semantic search over historical notes
- **Queue:** Celery + Redis — pipeline triggered daily at 6AM via Celery Beat
- **API:** FastAPI with SSE for real-time pipeline updates
- **Database:** PostgreSQL + Apache AGE + pgvector
- **Observability:** LangSmith (agent traces) + CloudWatch (API metrics)
- **Security:** Row Level Security — managers cannot access each other's data

## Key Design Decisions

| ADR | Decision | Rationale |
|-----|----------|-----------|
| 001 | Apache AGE for MAGMA graphs (MVP) | Single database, less infra complexity |
| 002 | AGE + PostgreSQL in same transaction | Atomic writes across relational + graph |
| 003 | Single-leader replication, read scaling | Followers absorb read load after 6AM |
| 004 | Typed AgentState with Pydantic | Schema changes caught at compile time |
| 005 | Fail Visible principle | Never deliver incomplete data silently |

Full ADR documentation in `/docs/adrs/`.

## Getting Started

See [DEPLOYMENT.md](DEPLOYMENT.md) for setup instructions.

## Project Structure

```
finagent/
├── app/
│   ├── api/              # FastAPI routers
│   ├── agents/           # LangGraph agents
│   │   ├── macro.py
│   │   ├── company.py
│   │   ├── quant.py
│   │   ├── risk.py
│   │   └── editor.py
│   ├── graph/            # LangGraph StateGraph
│   │   ├── state.py      # Typed AgentState
│   │   └── pipeline.py   # Graph definition
│   ├── memory/           # MAGMA implementation
│   │   ├── semantic.py
│   │   ├── temporal.py
│   │   ├── causal.py
│   │   └── entity.py
│   ├── db/               # Models + migrations
│   ├── services/         # Business logic
│   └── workers/          # Celery tasks
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── evals/            # Quality benchmarks
├── docs/
│   ├── adrs/             # Architecture Decision Records
│   └── architecture.md
├── docker-compose.yml
├── DEPLOYMENT.md
└── CLAUDE.md
```

## Invariants

These conditions must always be true. Every invariant has a corresponding integration test.

1. **Freshness** — no metric calculated without verifying `data_freshness`. Data older than 24h triggers a flag in the morning note.
2. **Data isolation** — no query without `WHERE gestor_id = ?`. PostgreSQL RLS enforces this at the database level.
3. **Fail Visible** — every data source failure generates an explicit flag. Morning notes are never delivered without indicating what is missing.

## Evals

Quality is measured over time, not just pass/fail. A fixed dataset of 20 market scenarios with known correct answers runs on every deploy. Results are stored with timestamps to track whether MAGMA is improving recommendation quality.

## Based On

- MAGMA: Multi-Graph Based Agentic Memory Architecture (ACL 2026) — arxiv.org/abs/2601.03236
- Designing Data-Intensive Applications — Martin Kleppmann
