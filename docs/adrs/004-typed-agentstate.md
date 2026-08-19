# ADR 004: Typed AgentState with Pydantic/TypedDict

## Status
Accepted (2026-07-24)

## Context
LangGraph requires a state schema. Options:
1. **Plain dict** — Flexible but no validation; runtime errors in production
2. **TypedDict** — Static type checking; defines required/optional fields
3. **Pydantic BaseModel** — Runtime validation; serialization; slower
4. **TypedDict + Pydantic output schemas** — Hybrid: static types for state, Pydantic for agent outputs

## Decision
Use **TypedDict for `AgentState`** (graph state) + **Pydantic models for agent output schemas** (`MacroOutput`, `CompanyEvent`, `QuantOutput`, `RiskFlag`, `Recommendation`).

Key design:
```python
class AgentState(TypedDict):
    pipeline_run_id: str
    morning_note_id: str
    manager_id: int
    company_ticker: str
    macro_context: MacroOutput | None
    company_events: list[CompanyEvent]
    quant_metrics: QuantOutput | None
    risk_flags: list[RiskFlag]
    morning_note: str | None
    recommendation: Recommendation | None
    confidence_scores: dict[str, float]
    data_freshness: Annotated[dict[str, datetime], merge_dicts]
    flags: Annotated[list[DataFlag], add]
```

Reducers (`merge_dicts`, `operator.add`) handle concurrent writes from parallel agents.

## Rationale
- **Static typing** — mypy catches missing/extra keys at compile time
- **LangGraph compatibility** — TypedDict is the native StateGraph state type
- **Reducers work** — `Annotated[..., add]` enables parallel agent merging
- **Performance** — No Pydantic validation overhead on every state transition
- **Runtime validation** — `validate_state()` function runs before each node (invariant checks)

## Consequences
- **Positive**: Type safety, parallel execution support, fast state updates
- **Negative**: Must keep TypedDict and Pydantic schemas in sync manually
- **Migration risk**: Schema changes require updating both TypedDict and Pydantic models

## Implementation Notes
- `app/graph/state.py` defines `AgentState`, reducers, `create_initial_state()`, `validate_state()`
- `InvalidStateError` raised if invariants violated (e.g., missing `manager_id`, invalid `RiskFlag.severity`)
- All 5 agent nodes wrapped with `validated_node()` decorator that calls `validate_state()` before execution