# ADR-036: Multi-Ticker SSE Events — Consolidated Per Agent Type

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Pradyumna (solo)
**Related Issues**: #122 (multi-ticker morning notes), ADR-031 (AgentState), ADR-032 (fan-out), ADR-035 (editor)

---

## Context

Current SSE events (single-ticker):
- `agent_started` — per agent
- `agent_completed` — per agent, includes `confidence_score`
- `note_ready` — single event with `morning_note_id`
- `pipeline_failed` — on fatal error

Multi-ticker graph (ADR-032): Company/Quant/Risk agents run via `map` pattern — N parallel iterations per agent type.

---

## Decision: Option B — Consolidated Events Per Agent Type

### Event Schema Changes

#### `agent_started` (unchanged, fires once per agent type)
```json
{
  "event_type": "agent_started",
  "agent_name": "company",
  "timestamp": "2026-10-28T12:00:00Z"
}
```

#### `agent_completed` (NEW: includes tickers array + aggregate metrics)
```json
{
  "event_type": "agent_completed",
  "agent_name": "company",
  "tickers": ["PETR4", "VALE3", "ITUB4"],
  "ticker_count": 3,
  "duration_ms": 2340,
  "avg_confidence_score": 0.82,
  "timestamp": "2026-10-28T12:00:02Z"
}
```

#### `note_ready` (unchanged — single note)
```json
{
  "event_type": "note_ready",
  "morning_note_id": "123",
  "tickers": ["PETR4", "VALE3", "ITUB4"],
  "timestamp": "2026-10-28T12:00:15Z"
}
```

#### `pipeline_failed` (unchanged)
```json
{
  "event_type": "pipeline_failed",
  "flags": [...],
  "timestamp": "..."
}
```

### Implementation: Wrapper Nodes Track Map Completion

Since LangGraph `map` runs iterations internally, we need wrapper nodes to emit consolidated events:

```python
# app/graph/pipeline.py - ADD WRAPPER NODES

async def company_wrapper(state: AgentState) -> dict:
    """Runs company map, emits consolidated SSE event on completion."""
    start = time.perf_counter()
    result = await company_map.ainvoke(state)  # LangGraph map node
    elapsed = (time.perf_counter() - start) * 1000
    
    tickers = state["company_tickers"]
    # Extract confidence scores from merged result
    confidences = result.get("confidence_scores", {})
    avg_conf = sum(confidences.get(t, {}).get("company", 1.0) for t in tickers) / len(tickers) if tickers else 1.0
    
    await sse_service.emit_event(state["pipeline_run_id"], {
        "event_type": "agent_completed",
        "agent_name": "company",
        "tickers": tickers,
        "ticker_count": len(tickers),
        "duration_ms": round(elapsed),
        "avg_confidence_score": round(avg_conf, 2),
        "timestamp": datetime.now(UTC).isoformat()
    })
    return result

# Same pattern for quant_wrapper, risk_wrapper
```

**Graph edges**:
```python
builder.add_edge("macro", "company_wrapper")
builder.add_edge("company_wrapper", "quant_wrapper")
builder.add_edge("quant_wrapper", "risk_wrapper")
builder.add_edge("risk_wrapper", "consolidate")
```

### Alternative: Post-Map Hook (If LangGraph Supports)

If LangGraph 1.2+ has map completion callbacks, use those instead of wrapper nodes. But wrapper nodes are explicit and version-agnostic.

---

## Consequences

### Positive
- **Frontend simplicity** — one progress bar per agent type, not per ticker
- **Lower SSE overhead** — 4 `agent_completed` events vs 4 × N
- **Meaningful metrics** — `duration_ms` for entire agent type, `avg_confidence_score`
- **Backward compatible** — single-ticker case: `tickers: ["PETR4"]`, `ticker_count: 1`

### Negative / Risks
- **Wrapper nodes add graph complexity** — extra nodes just for SSE
- **All-or-nothing visibility** — if 1 of 5 tickers fails in CompanyAgent, event still fires with partial results (check `flags` for failures)
- **Latency** — event fires after ALL tickers complete (not streaming per ticker)

---

## Migration Path

1. **Add wrapper nodes** in `app/graph/pipeline.py` for company, quant, risk
2. **Update `sse_service.emit_event`** calls in wrapper nodes
3. **Update frontend** (if exists) to handle `tickers` array in `agent_completed`
4. **Test** — verify event timing and payload with 3+ tickers

---

## Testing

| Test | Scope |
|------|-------|
| `tests/integration/test_sse_multi_ticker.py` | SSE events fire with correct tickers array, duration, avg confidence |
| `tests/unit/test_sse_payload.py` | Event schema validation for multi-ticker payloads |

---

## References

- ADR-031: Multi-Ticker AgentState & Graph
- ADR-032: Fan-out — LangGraph `map` pattern
- ADR-013: SSE Event Format (original)
- `app/services/sse.py` — SSE service
- `app/graph/pipeline.py` — graph definition