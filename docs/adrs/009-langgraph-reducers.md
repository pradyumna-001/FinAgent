# ADR 009: LangGraph Reducers for Parallel Agent Execution

## Status
Accepted (2026-08-18)

## Context
LangGraph StateGraph runs `company_agent` and `quant_agent` in parallel after `macro_agent`. Both write to shared state keys:
- `data_freshness` — both add timestamp for their domain
- `flags` — both append `DataFlag` objects

Standard state update would overwrite; need merge semantics.

## Decision
Use **LangGraph reducers** via `Annotated` type hints:
```python
data_freshness: Annotated[dict[str, datetime], merge_dicts]
flags: Annotated[list[DataFlag], add]
```

Where:
- `merge_dicts(left, right) -> {**left, **right}` — dict union (later wins)
- `operator.add` — list concatenation

Agents return **partial state dicts** (only modified keys):
```python
# company_agent_node returns:
{"company_events": [...], "data_freshness": {"company": now}, "flags": [flag1]}

# quant_agent_node returns:
{"quant_metrics": {...}, "data_freshness": {"quant": now}, "flags": [flag2]}
```

LangGraph merges via reducers automatically.

## Rationale
- **Correct parallelism** — Only way to safely merge concurrent writes to same keys
- **LangGraph native** — No custom merge logic; reducer is declarative
- **Type-safe** — `Annotated` preserves type information for mypy
- **Testable** — Integration tests simulate reducer with `merge_result()` helper

## Consequences
- **Positive**: Clean parallel execution; no race conditions
- **Negative**: Agents must return partial dicts (not full state); test helpers needed
- **Learning curve**: Reducer pattern is LangGraph-specific

## Implementation Notes
- `app/graph/state.py` defines `merge_dicts` and uses `Annotated[..., add]` for flags
- All 5 agent nodes refactored to return partial dicts (commit `fbff7da`)
- `tests/integration/test_agents.py` uses `merge_result()` to simulate reducer in tests
- `dev_graph` uses `InMemorySaver`; production uses `AsyncPostgresSaver`