# ADR-038: Test Migration Strategy — Incremental with Adapter

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Pradyumna (solo)
**Related Issues**: #122 (multi-ticker morning notes), all ADR-030 through ADR-037

---

## Context

`create_initial_state` signature changes from:
```python
create_initial_state(manager_id: int, company_ticker: str, pipeline_run_id: str, morning_note_id: str)
```
to:
```python
create_initial_state_multi(manager_id: int, company_tickers: list[str], pipeline_run_id: str, morning_note_id: str)
```

**75 call sites** across:
- Unit tests (macro, company, quant, risk, editor, approval_gate)
- Integration tests (agents, graph_pipeline, approval_gate, SSE)
- Scripts (run_*.py, debug_*.py, verify_pipeline.py)
- Demo (demo_br_pn.py)

---

## Decision: Strategy B — Incremental Migration with Adapter

### Adapter Pattern

```python
# app/graph/state.py

def create_initial_state(
    *,
    manager_id: int,
    company_ticker: str,                    # DEPRECATED: single
    company_tickers: list[str] | None = None,  # NEW: list (optional)
    pipeline_run_id: str,
    morning_note_id: str
) -> AgentState:
    """Backward-compatible wrapper. Use create_initial_state_multi for new code."""
    if company_tickers is not None:
        tickers = company_tickers
    else:
        tickers = [company_ticker]
        import warnings
        warnings.warn(
            "create_initial_state(company_ticker=...) is deprecated; "
            "use create_initial_state_multi(company_tickers=[...])",
            DeprecationWarning,
            stacklevel=2
        )
    
    return create_initial_state_multi(
        manager_id=manager_id,
        company_tickers=tickers,
        pipeline_run_id=pipeline_run_id,
        morning_note_id=morning_note_id
    )

def create_initial_state_multi(
    *,
    manager_id: int,
    company_tickers: list[str],
    pipeline_run_id: str,
    morning_note_id: str
) -> AgentState:
    """NEW: Multi-ticker initial state."""
    return {
        "manager_id": manager_id,
        "company_tickers": company_tickers,
        "pipeline_run_id": pipeline_run_id,
        "morning_note_id": morning_note_id,
        "macro_context": {},
        "company_events": {},
        "quant_metrics": {},
        "risk_flags": {},
        "portfolio_risk_flags": [],
        "portfolio_data_flags": [],
        "sector_weights": {},
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

### Migration Batches (Sequential, Verifiable)

| Batch | Files | Call Sites | Verification |
|-------|-------|------------|--------------|
| **1** | `tests/unit/test_macro_agent.py`, `test_company_agent.py`, `test_quant_agent.py`, `test_risk_agent.py`, `test_editor_agent.py` | ~15 | `pytest tests/unit/ -v` passes |
| **2** | `tests/unit/test_approval_gate.py` | ~5 | `pytest tests/unit/test_approval_gate.py -v` passes |
| **3** | `tests/integration/test_agents.py`, `test_graph_pipeline.py` | ~10 | `pytest tests/integration/test_agents.py tests/integration/test_graph_pipeline.py -v` passes |
| **4** | `tests/integration/test_approval_gate.py`, `test_sse.py` | ~10 | `pytest tests/integration/test_approval_gate.py tests/integration/test_sse.py -v` passes |
| **5** | `scripts/run_macro_agent.py`, `run_company_agent.py`, `run_quant_agent.py`, `run_risk_agent.py`, `run_pipeline.py`, `debug_agents.py`, `verify_pipeline.py` | ~15 | Each script runs without error |
| **6** | `demo_br_pn.py` | ~5 | Demo runs |
| **7** | **Cleanup**: Remove `create_initial_state` wrapper, rename `create_initial_state_multi` → `create_initial_state`, remove deprecation warning | — | Full test suite passes, no deprecation warnings |

**Rule**: Each batch must pass **all existing tests** before next batch. No test modifications that change behavior — only signature updates.

---

## Consequences

### Positive
- **Zero downtime** — CI passes throughout migration
- **Granular rollback** — if batch 3 breaks, revert batch 3 only
- **Parallelizable** — multiple developers can migrate different batches
- **Learning curve** — team adapts to new state structure gradually

### Negative / Risks
- **Temporary duplication** — two functions coexist (~2 weeks)
- **Deprecation warnings** — test output noise (suppress with `-W ignore::DeprecationWarning` if needed)
- **Mental overhead** — reviewers must check which function is used

---

## Cleanup (Batch 7)

```python
# app/graph/state.py - AFTER all migrations

def create_initial_state(
    *,
    manager_id: int,
    company_tickers: list[str],
    pipeline_run_id: str,
    morning_note_id: str
) -> AgentState:
    """Multi-ticker initial state. Replaces create_initial_state_multi."""
    return {
        "manager_id": manager_id,
        "company_tickers": company_tickers,
        "pipeline_run_id": pipeline_run_id,
        "morning_note_id": morning_note_id,
        "macro_context": {},
        "company_events": {},
        "quant_metrics": {},
        "risk_flags": {},
        "portfolio_risk_flags": [],
        "portfolio_data_flags": [],
        "sector_weights": {},
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

---

## Testing

| Test | Scope |
|------|-------|
| Each batch | `pytest` passes for modified files only |
| Final | Full test suite passes, no deprecation warnings in output |

---

## References

- All ADR-030 through ADR-037 (multi-ticker architecture)
- `app/graph/state.py` — current `create_initial_state`
- `grep -r "create_initial_state" --include="*.py"` — all 75 call sites