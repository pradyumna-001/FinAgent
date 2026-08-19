# CLAUDE.md — FinAgent

Context file for Claude Code. Read this before touching any file.

---

## What this project is

FinAgent is a multi-agent AI system that generates daily morning notes and buy/sell recommendations for Brazilian equities (B3). It is a copilot for asset managers — not a replacement. The manager reviews, edits, and signs every recommendation.

**Target users:** Asset management professionals (early adopters).
**Pricing:** To be determined (personal project).
**Stack:** LangGraph, FastAPI, PostgreSQL + Apache AGE + pgvector, Redis, Celery, AWS.

---

## Architecture overview

```
Celery Beat (6AM daily)
    ↓
Pipeline Task
    ↓
MacroAgent (web search → macro context)
    ↓
CompanyAgent ←→ QuantAgent  (parallel via LangGraph)
    ↓               ↓
        RiskAgent (adversarial agent)
            ↓
        EditorAgent (morning note + recommendation)
            ↓
    PostgreSQL (morning_notes, recommendations)
    Apache AGE (MAGMA memory graphs)
    SSE event → manager's browser
```

---

## Non-negotiable rules

**Never violate these. Ask before changing anything that touches them.**

### 1. Fail Visible
Every data source failure must generate an explicit flag in the morning note. Never deliver a silent incomplete report.

```python
# CORRECT
if data_age > timedelta(hours=24):
    state["flags"].append(DataFlag(
        source="b3_api",
        reason="data_outdated",
        field="pe_ratio",
        message="P/L desatualizado — dado de 48h atrás"
    ))

# WRONG — never silently use stale data
pe_ratio = data.get("pe_ratio", None)
```

### 2. Data freshness before calculation
QuantAgent must verify `data_freshness` before calculating any metric. No exceptions.

```python
# CORRECT
def calculate_metrics(data: QuantData) -> QuantOutput:
    if data.freshness_age > timedelta(hours=24):
        return QuantOutput(flagged=True, reason="data_outdated")
    # only then calculate

# WRONG
def calculate_metrics(data: QuantData) -> QuantOutput:
    return QuantOutput(pe_ratio=data.price / data.earnings)
```

### 3. gestor_id in every query
No query without `WHERE gestor_id = ?`. PostgreSQL RLS enforces this at DB level, but application code must also set it explicitly.

```python
# CORRECT
async def get_morning_notes(gestor_id: int, db: AsyncSession):
    return await db.execute(
        select(MorningNote).where(MorningNote.gestor_id == gestor_id)
    )

# WRONG — never query without gestor_id filter
async def get_morning_notes(db: AsyncSession):
    return await db.execute(select(MorningNote))
```

### 4. Typed AgentState always
Never use plain dicts in the agent state. Always use the typed AgentState.

```python
# CORRECT — in app/graph/state.py
class AgentState(TypedDict):
    pipeline_run_id: str
    morning_note_id: str
    gestor_id: int
    empresa_ticker: str
    macro_context: MacroOutput | None
    company_events: list[CompanyEvent]
    quant_metrics: QuantOutput | None
    risk_flags: list[RiskFlag]
    morning_note: str | None
    recommendation: Recommendation | None
    confidence_scores: dict[str, float]
    data_freshness: dict[str, datetime]
    flags: list[DataFlag]

# WRONG
state = {"macro": "...", "company": "..."}
```

### 5. Atomic writes — morning note + MAGMA
Always write morning_note, recommendation, and MAGMA graph update in the same transaction.

```python
# CORRECT
async with session.begin():
    session.add(MorningNote(...))
    session.add(Recommendation(...))
    await session.execute(text("SELECT * FROM cypher('magma', $$...$$) AS (v agtype)"))
# COMMIT covers relational + AGE graph

# WRONG — split writes
await session.execute(insert(MorningNote(...)))
await session.commit()
await update_magma_graph(...)  # if this fails, inconsistency
```

### 6. Secrets handling

No plaintext secrets in any tracked file. CI env uses `${{ secrets.X }}`; docker-compose uses `${VAR:-default}`. `.env.*` files are gitignored. Local dev defaults are fine when they describe only a localhost-bound dev container, but provider keys (Tavily, NVIDIA, OpenRouter, DeepSeek, AWS, etc.) are NEVER committed — they live in `gh secret set` / the GitHub web UI or `.env` (gitignored).

If a secret lands in git history (any branch):
1. **Rotate at the provider FIRST.** History scrubbing does not undo exposure; a leaked-and-then-scrubbed secret is still compromised.
2. Confirm GitHub Secret Scanning — custom patterns can be added to catch unknown provider formats (Tavily/NVIDIA were not in the default list during the 2026-08-14 incident).
3. Scrub with `git filter-repo --replace-text`, replacing the literal with `${{ secrets.X }}` (or `${VAR:-default}` for shell contexts). Be specific with replacement strings — a single global substring replace can corrupt Python files where the literal was a hardcoded default.
4. Force-push affected branches from a fresh mirror clone. `main` is protected with `enforce_admins: true`; lifting protection (`DELETE /branches/main/protection`) to force-push and immediately restoring it via PUT is the documented breach path.
5. Set the rotated key as a GitHub Actions secret so post-scrub CI green.
6. Write an incident record at `docs/journal/new/1_week/` (or wherever the journal lives) —Rotate-then-Scrub order is non-negotiable.

```yaml
# CORRECT — .github/workflows/*.yml
env:
  TAVILY_API_KEY: ${{ secrets.TAVILY_API_KEY }}
  NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}

# CORRECT — docker-compose.yml
environment:
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-finagent_secure_pass}

# WRONG — provider keys committed as literals
env:
  TAVILY_API_KEY: tvly-dev-3x4mpl3K3y0vAl1dL00ksR3al
```

---

## Correlation IDs — always log all three

Every log line must include the three correlation IDs:

```python
logger.info(
    "Agent completed",
    extra={
        "pipeline_run_id": state["pipeline_run_id"],
        "morning_note_id": state["morning_note_id"],
        "agent": "MacroAgent",
        "duration_ms": elapsed,
        "confidence": state["confidence_scores"].get("macro"),
    }
)
```

---

## Agent responsibilities — never mix them

| Agent | Responsibility | Must NOT do |
|-------|---------------|-------------|
| MacroAgent | Macro context (Selic, inflation, FX) | Calculate company metrics |
| CompanyAgent | Company news and events | Make buy/sell calls |
| QuantAgent | Financial metrics from APIs only | Interpret news |
| RiskAgent | Question other agents' outputs | Generate the final note |
| EditorAgent | Consolidate into morning note | Fetch new data |

If you find logic in the wrong agent, move it before adding new code.

---

## LLM usage — cost control

```python
# Fast model (cheap) — extraction and summarization
FAST_MODEL = "gpt-4o-mini"  # MacroAgent, CompanyAgent

# Smart model (expensive) — reasoning and synthesis
SMART_MODEL = "gpt-4o"      # RiskAgent, EditorAgent

# QuantAgent does NOT use LLM for calculations
# Only uses LLM to interpret results
```

---

## Testing requirements

Before any PR:

```bash
# Must pass
pytest tests/unit/ -v
pytest tests/integration/ -v

# Must not regress
pytest tests/evals/ -v --compare-baseline
```

The three invariant tests must always pass:

```
tests/integration/test_invariants.py::test_data_freshness_invariant
tests/integration/test_invariants.py::test_rls_isolation_invariant
tests/integration/test_invariants.py::test_fail_visible_invariant
```

---

## ADR index

| ADR | Title | Status |
|-----|-------|--------|
| 001 | Apache AGE for MAGMA graphs (MVP) | Accepted |
| 002 | AGE + PostgreSQL in same transaction | Accepted |
| 003 | Single-leader replication, read scaling | Accepted |
| 004 | Typed AgentState with Pydantic | Accepted |
| 005 | Fail Visible principle | Accepted |
| 006 | Backpressure via CELERYD_CONCURRENCY | Accepted |
| 007 | Fast/smart LLM routing per agent | Accepted |

Full ADRs in `/docs/adrs/`.

---

## Progress tracker

### Phase 1 — Foundation (Week 1)
- [ ] Repository structure
- [ ] Docker Compose (PostgreSQL + AGE + pgvector, Redis, Celery)
- [ ] SQLAlchemy models (Manager, Company, Portfolio, MorningNote, Recommendation)
- [ ] Alembic migrations + RLS policies
- [ ] FastAPI base + /health endpoint
- [ ] GitHub Actions CI

### Phase 2 — Agents (Week 2-3)
- [ ] Typed AgentState
- [ ] MacroAgent (Tavily web search)
- [ ] CompanyAgent (Tavily + CVM)
- [ ] QuantAgent (B3/Yahoo Finance API — NO LLM for calculations)
- [ ] RiskAgent (adversarial)
- [ ] EditorAgent (consolidation)
- [ ] LangGraph StateGraph with parallel execution
- [ ] LangSmith integration with correlation ID tags

### Phase 3 — MAGMA (Week 4-5)
- [ ] Study MAGMA paper (arxiv.org/abs/2601.03236)
- [ ] Implement 4 graphs in Apache AGE
- [ ] Policy-guided traversal (RL component)
- [ ] Integration with EditorAgent memory reads
- [ ] Atomic transaction: morning_note + recommendation + MAGMA update

### Phase 4 — API + Pipeline (Week 6)
- [ ] POST /pipeline/trigger
- [ ] GET /morning-notes (with RLS)
- [ ] GET /morning-notes/{id}/stream (SSE)
- [ ] POST /recommendations/{id}/feedback
- [ ] Celery Beat schedule (6AM daily)
- [ ] Backpressure configuration

### Phase 5 — Tests + Evals (Week 7)
- [ ] Unit tests (freshness check, confidence threshold, flag generation)
- [ ] Integration tests (3 invariants)
- [ ] E2E test (full pipeline with real LLM)
- [ ] Evals dataset (20 market scenarios with known answers)
- [ ] Eval runner + baseline comparison

### Phase 6 — Deploy (Week 8)
- [ ] AWS RDS with pgvector + AGE
- [ ] AWS ECS (FastAPI + Celery)
- [ ] ElastiCache Redis
- [ ] CloudWatch dashboard + alarms
- [ ] Onboard first 3 managers

---

## MAGMA implementation notes

Based on: arxiv.org/abs/2601.03236
Repository: github.com/FredJiang0324/MAGMA

Study sequence before implementing:
1. Read full paper
2. Run their tests on LoCoMo dataset
3. Understand policy-guided traversal (RL component)
4. Design your version before writing code
5. Benchmark your implementation vs pgvector baseline

The benchmark result goes in the README and the resume.

---

## Known limitations (MVP)

- Apache AGE is less mature than Neo4j — expect edge cases
- No fine-tuning — using base GPT-4o
- B3 API has 15-min delay on free tier — morning notes are for analysis, not intraday trading
- Track record requires 30+ days of data to be meaningful
- MAGMA RL component may be simplified to rule-based traversal initially
