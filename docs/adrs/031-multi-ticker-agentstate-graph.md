# ADR-031: Multi-Ticker AgentState & Graph Architecture

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Pradyumna (solo)
**Related Issues**: #122 (multi-ticker morning notes), ADR-030 (schema), ADR-004 (typed AgentState), ADR-009 (LangGraph reducers)

---

## Context

Issue #122 requires: **one morning note per manager per portfolio per day**, with per-ticker recommendations in JSONB.

Current `AgentState` (ADR-004) is single-ticker:
- `company_ticker: str`
- `company_events: list[CompanyEvent]`
- `quant_metrics: QuantOutput | None`
- `risk_flags: list[RiskFlag]`
- `recommendation: RecommendationPayload | None`
- `confidence_scores: dict[str, float]` (keys: macro, company, quant, risk, overall)

Graph: `macro → [company, quant] parallel → risk → editor → persist → send → approval_gate → finalize`

---

## Decision

### 1. AgentState Changes (Dict-Keyed-By-Ticker)

```python
# app/graph/state.py

class AgentState(TypedDict):
    # Run identifiers
    pipeline_run_id: str
    morning_note_id: str
    manager_id: int
    
    # NEW: All tickers for this portfolio
    company_tickers: list[str]                    # ["PETR4", "VALE3", "ITUB4"]
    
    # Per-ticker data — merge_dicts reducer (shallow merge by key)
    macro_context: Annotated[dict[str, MacroOutput], merge_dicts]              # key = "global"
    company_events: Annotated[dict[str, list[CompanyEvent]], merge_dicts]      # {"PETR4": [...], "VALE3": [...]}
    quant_metrics: Annotated[dict[str, QuantOutput | None], merge_dicts]       # {"PETR4": {...}, "VALE3": None}
    risk_flags: Annotated[dict[str, list[RiskFlag]], merge_dicts]              # {"PETR4": [...], "VALE3": [...]}
    
    # Portfolio-level (from Consolidate node)
    portfolio_risk_flags: list[RiskFlag]          # Sector concentration, etc.
    portfolio_data_flags: list[DataFlag]          # Aggregate data quality flags
    sector_weights: dict[str, float]              # {"Energy": 0.45, "Financial": 0.30}
    
    # Editor output (consolidated)
    morning_note: str | None
    recommendations: Annotated[dict[str, RecommendationPayload], merge_dicts]  # {"PETR4": {...}, "VALE3": {...}}
    confidence_scores: Annotated[dict[str, dict[str, float]], merge_dicts]     # {"PETR4": {"macro": 0.9, ...}, ...}
    
    # Shared/reducer fields
    data_freshness: Annotated[dict[str, datetime], merge_dicts]   # per-ticker + "macro" + "portfolio"
    flags: Annotated[list[DataFlag], add]
    
    # Persistence/output
    recommendation_id: int | None   # Single MorningNote ID
    manager_decision: str | None
    decision_channel: str | None
```

**Reducer behavior**: `merge_dicts = {**left, **right}` — parallel nodes for different tickers write to different keys → clean merge.

### 2. Graph Architecture: Option Z (Consolidate Node)

```
START → macro → [company, quant, risk]_per_ticker → merge → consolidate → editor → persist → send → approval_gate → finalize → END
```

**Fan-out**: For N tickers, CompanyAgent/QuantAgent/RiskAgent run N times in parallel (LangGraph `Send` API or `map` pattern).

**Consolidate node** (Python, no LLM):
- Input: merged per-ticker dicts + `company_tickers` list
- Computes:
  - `sector_weights` from `Company.sector` (joined via tickers)
  - Concentration flags → `portfolio_risk_flags`
  - Stale ticker count → `portfolio_data_flags`
- Output: portfolio-level fields added to state

**EditorAgent**: Receives full state (per-ticker dicts + portfolio fields) → generates single consolidated note with per-ticker sections + "Portfolio Risk" section.

### 3. Pipeline Trigger: One Task Per Manager Per Portfolio

**Celery Beat schedule**: 
```python
beat_schedule = {
    "run-daily-pipeline-per-portfolio": {
        "task": "app.workers.pipeline.run_daily_pipeline_for_portfolio",
        "schedule": crontab(hour=9, minute=0),
        "kwargs": {"manager_id": 1, "portfolio_id": 1},  # Dynamic: iterate all active portfolios
    }
}
```

**Worker task** (`app/workers/pipeline.py`):
```python
@celery_app.task(bind=True, ignore_result=True)
def run_daily_pipeline_for_portfolio(self, manager_id: int, portfolio_id: int) -> None:
    # Fetch tickers for this portfolio
    async with SessionLocal() as session:
        result = await session.execute(
            select(Company.ticker)
            .join(PortfolioHolding, PortfolioHolding.company_id == Company.id)
            .where(PortfolioHolding.portfolio_id == portfolio_id)
        )
        tickers = [row[0] for row in result]
    
    if not tickers:
        logger.info("portfolio_empty", portfolio_id=portfolio_id)
        return
    
    # Single graph run for all tickers
    pipeline_run_id = uuid4()
    morning_note_id = uuid4()
    initial = create_initial_state(
        manager_id=manager_id,
        company_tickers=tickers,
        pipeline_run_id=str(pipeline_run_id),
        morning_note_id=str(morning_note_id)
    )
    await _graph.ainvoke(initial, config={"configurable": {"thread_id": str(pipeline_run_id)}})
```

**API trigger** (`app/schemas/pipeline.py`):
```python
class TriggerRequest(BaseModel):
    manager_id: int
    portfolio_id: int
    # company_id: REMOVED
```

### 4. `create_initial_state` Signature Change

```python
def create_initial_state(
    *,
    manager_id: int,
    company_tickers: list[str],        # CHANGED: was company_ticker: str
    pipeline_run_id: str,
    morning_note_id: str
) -> AgentState:
    return {
        "manager_id": manager_id,
        "company_tickers": company_tickers,
        "pipeline_run_id": pipeline_run_id,
        "morning_note_id": morning_note_id,
        "macro_context": {},
        "company_events": {},
        "quant_metrics": {},
        "risk_flags": {},
        "morning_note": None,
        "recommendations": {},
        "confidence_scores": {},
        "data_freshness": {},
        "flags": [],
        "recommendation_id": None,
        "manager_decision": None,
        "decision_channel": None
    }
```

### 5. MacroAgent Output Key

```python
# app/agents/macro.py
async def macro_agent_node(state: AgentState) -> dict:
    # ... fetch macro ...
    return {
        "macro_context": {"global": macro_output},  # KEY = "global"
        "data_freshness": {"macro": datetime.now(UTC)},
        "flags": new_flags
    }
```

---

## Consequences

### Positive
- **Parallel per-ticker execution** — LangGraph fans out Company/Quant/Risk per ticker, merges via `merge_dicts`
- **Portfolio-level risk in Python** — deterministic, no LLM cost, extensible
- **Single MorningNote per portfolio** — matches product requirement
- **LangSmith traceability** — each parallel node tagged with ticker via state keys
- **Backward-compatible reducers** — `merge_dicts` handles dict merge naturally

### Negative / Risks
- **All per-ticker fields become dicts** — every agent, test, and prompt must update
- **Fan-out complexity** — LangGraph `Send` API or `map` needed for dynamic ticker count
- **EditorAgent prompt rewrite** — must iterate tickers, handle missing keys
- **Migration scope** — touches `state.py`, all agents, prompts, tests, worker, API, schemas

---

## Testing

| Test | Scope |
|------|-------|
| `tests/unit/test_state_multi_ticker.py` | `create_initial_state` with list; reducer merges dicts correctly |
| `tests/integration/test_graph_fanout.py` | Graph runs N parallel Company/Quant/Risk nodes; merges correctly |
| `tests/integration/test_consolidate_node.py` | Consolidate computes sector weights, concentration flags |
| `tests/integration/test_editor_multi_ticker.py` | Editor generates consolidated note with all sections |
| `tests/integration/test_worker_portfolio.py` | Worker fetches tickers, calls graph once per portfolio |

---

## Migration Path

1. **ADR-030 migrations** (schema) — Phase 1-2 complete
2. **AgentState changes** — `state.py` + `create_initial_state`
3. **Graph restructure** — add Consolidate node, fan-out pattern
4. **Agent updates** — Macro (global key), Company/Quant/Risk (per-ticker output), Editor (consolidated prompt)
5. **Worker + API** — new task signature, trigger schema
6. **Tests** — update all test state factories
7. **Deploy** — with ADR-030 Phase 3-4

---

## Future Work

- **PortfolioRiskAgent** (LLM) after Consolidate for qualitative cross-ticker analysis
- **Dynamic fan-out** via LangGraph `Send` API (current: static graph, need runtime ticker list)
- **Per-ticker approval** — if gestor wants to approve/reject per ticker, extend `recommendations` JSONB with `manager_decision` per ticker

---

## References

- ADR-004: Typed AgentState
- ADR-009: LangGraph Reducers (`merge_dicts`)
- ADR-030: Multi-Ticker Database Schema
- `app/graph/state.py` — current AgentState
- `app/workers/pipeline.py` — current Celery task
- `app/schemas/pipeline.py` — TriggerRequest
- `docs/issues.md` — Issue #122 spec