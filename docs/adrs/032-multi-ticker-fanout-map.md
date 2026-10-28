# ADR-032: Multi-Ticker Fan-Out — LangGraph `map` Pattern

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Pradyumna (solo)
**Related Issues**: #122 (multi-ticker morning notes), ADR-030 (schema), ADR-031 (AgentState & graph), ADR-009 (LangGraph reducers)

---

## Context

Issue #122 requires running CompanyAgent, QuantAgent, RiskAgent **once per ticker** in parallel for N tickers (typically 5-10), merging outputs via `merge_dicts` reducers into dict-keyed-by-ticker state.

LangGraph version: **1.2.11** (≥ 0.2.0) — `map` pattern available.

---

## Decision: Option C — `map` Pattern

```python
# app/graph/pipeline.py
from langgraph.graph import END, START, StateGraph
from app.agents.company import company_agent_node
from app.agents.quant import quant_agent_node
from app.agents.risk import risk_agent_node
from app.agents.consolidate import consolidate_node
from app.agents.macro import macro_agent_node
from app.agents.editor import editor_agent_node
from app.agents.persist import persist_recommendation_node
from app.agents.send import send_note_node
from app.agents.approval_gate import approval_gate_node
from app.agents.finalize import finalize_morning_note_node
from app.graph.serialization import get_serializer
from app.graph.state import AgentState, InvalidStateError, create_initial_state

def validated_node(node_fn, name: str):
    async def wrapper(state: AgentState) -> AgentState:
        InvalidStateError().validate(state)
        return await node_fn(state)
    wrapper.__name__ = name
    return wrapper

builder = StateGraph(AgentState)

# Macro runs once (global context)
builder.add_node("macro", validated_node(macro_agent_node, "macro"))

# Fan-out per ticker using map pattern
# Each agent receives sliced state with single ticker, outputs dict-keyed-by-ticker
builder.add_node("company", validated_node(company_agent_node, "company")).map(
    lambda state: [
        {"current_ticker": t, "company_tickers": [t]} 
        for t in state["company_tickers"]
    ]
)
builder.add_node("quant", validated_node(quant_agent_node, "quant")).map(
    lambda state: [
        {"current_ticker": t, "company_tickers": [t]} 
        for t in state["company_tickers"]
    ]
)
builder.add_node("risk", validated_node(risk_agent_node, "risk")).map(
    lambda state: [
        {"current_ticker": t, "company_tickers": [t]} 
        for t in state["company_tickers"]
    ]
)

# Consolidate runs once on merged per-ticker state
builder.add_node("consolidate", validated_node(consolidate_node, "consolidate"))

# Editor runs once on full state (per-ticker + portfolio)
builder.add_node("editor", validated_node(editor_agent_node, "editor"))

# Persistence & delivery (unchanged)
builder.add_node("persist", validated_node(persist_recommendation_node, "persist"))
builder.add_node("send", validated_node(send_note_node, "send"))
builder.add_node("approval_gate", validated_node(approval_gate_node, "approval_gate"))
builder.add_node("finalize", validated_node(finalize_morning_note_node, "finalize"))

# Edges
builder.add_edge(START, "macro")
builder.add_edge("macro", "company")
builder.add_edge("company", "quant")
builder.add_edge("quant", "risk")
builder.add_edge("risk", "consolidate")
builder.add_edge("consolidate", "editor")
builder.add_edge("editor", "persist")
builder.add_edge("persist", "send")
builder.add_edge("send", "approval_gate")
builder.add_edge("approval_gate", "finalize")
builder.add_edge("finalize", END)

def compile_graph(checkpointer) -> CompiledStateGraph:
    return builder.compile(checkpointer=checkpointer)

_dev_saver = InMemorySaver()
_dev_saver.serde = get_serializer()
dev_graph = builder.compile(checkpointer=_dev_saver)

__all__ = ["compile_graph", "dev_graph", "create_initial_state"]
```

---

## Agent Signature Changes Required

All per-ticker agents (Company, Quant, Risk) must be updated:

### Input: Sliced State
```python
# Before: state["company_ticker"] → str
# After:  state["current_ticker"] → str (injected by map)
```

### Output: Dict-Keyed-By-Ticker (for `merge_dicts` reducer)
```python
# CompanyAgent
async def company_agent_node(state: AgentState) -> dict:
    ticker = state["current_ticker"]
    events = await fetch_company_events(ticker)
    return {
        "company_events": {ticker: events},  # DICT, not list
        "data_freshness": {ticker: datetime.now(UTC)},
        "flags": new_flags
    }

# QuantAgent
async def quant_agent_node(state: AgentState) -> dict:
    ticker = state["current_ticker"]
    metrics = await fetch_quant_metrics(ticker)
    return {
        "quant_metrics": {ticker: metrics},  # DICT
        "data_freshness": {ticker: datetime.now(UTC)},
        "flags": new_flags
    }

# RiskAgent
async def risk_agent_node(state: AgentState) -> dict:
    ticker = state["current_ticker"]
    # Reads per-ticker data from merged state:
    company_events = state["company_events"].get(ticker, [])
    quant_metrics = state["quant_metrics"].get(ticker)
    macro_context = state["macro_context"].get("global")
    ...
    return {
        "risk_flags": {ticker: risk_flags},  # DICT
        "data_freshness": {ticker: datetime.now(UTC)},
        "flags": new_flags
    }
```

**MacroAgent** (unchanged — runs once):
```python
async def macro_agent_node(state: AgentState) -> dict:
    macro = await fetch_macro()
    return {
        "macro_context": {"global": macro},  # KEY = "global"
        "data_freshness": {"macro": datetime.now(UTC)},
        "flags": new_flags
    }
```

---

## Consolidate Node (New)

```python
# app/agents/consolidate.py
from app.graph.state import AgentState
from app.db.session import SessionLocal
from app.db.models import Company
from sqlalchemy import select
from app.utils.flags import DataFlag, Severity

async def consolidate_node(state: AgentState) -> dict:
    tickers = state["company_tickers"]
    
    # Fetch sectors for all tickers
    async with SessionLocal() as session:
        result = await session.execute(
            select(Company.ticker, Company.sector)
            .where(Company.ticker.in_(tickers))
        )
        sectors = {row[0]: row[1] or "Unknown" for row in result}
    
    # Compute sector weights from portfolio holdings (simplified: equal weight)
    # TODO: Use actual PortfolioHolding.weight when available
    sector_weights = {}
    for t in tickers:
        sector = sectors.get(t, "Unknown")
        sector_weights[sector] = sector_weights.get(sector, 0) + 1 / len(tickers)
    
    # Portfolio risk flags
    portfolio_risk_flags = []
    for sector, weight in sector_weights.items():
        if weight > 0.4:
            portfolio_risk_flags.append({
                "probability": 0.8,
                "impact": "high",
                "description": f"Sector concentration: {sector} = {weight:.0%}",
                "severity": "WARNING"
            })
    
    # Portfolio data flags (stale tickers)
    stale_count = sum(
        1 for t in tickers
        if state["data_freshness"].get(t) and (datetime.now(UTC) - state["data_freshness"][t]).total_seconds() > 86400
    )
    portfolio_data_flags = []
    if stale_count > 0:
        portfolio_data_flags.append(DataFlag(
            source="consolidate",
            severity=Severity.WARNING,
            message=f"{stale_count}/{len(tickers)} tickers have stale data (>24h)"
        ))
    
    return {
        "sector_weights": sector_weights,
        "portfolio_risk_flags": portfolio_risk_flags,
        "portfolio_data_flags": portfolio_data_flags,
        "data_freshness": {"portfolio": datetime.now(UTC)},
        "flags": []
    }
```

---

## Consequences

### Positive
- **Dynamic fan-out** — handles any portfolio size (1 to 50+ tickers)
- **Clean graph** — 4 nodes (company, quant, risk, consolidate) vs 60+ static
- **Native reducer merge** — `merge_dicts` automatically combines per-ticker dicts
- **LangSmith traceability** — each map iteration appears as separate node in trace
- **Isolation** — ticker failure doesn't block others (LangGraph map handles errors per iteration)

### Negative / Risks
- **Agent rewrites required** — Company, Quant, Risk agents must accept sliced state + output dict-keyed
- **Map error handling** — need to verify LangGraph 1.2 behavior when one iteration fails (does it stop others?)
- **State slicing boilerplate** — each agent extracts `current_ticker`, wraps output in dict
- **Testing complexity** — must test map behavior with various ticker counts

---

## Migration Path

1. **Add `consolidate_node`** — new file `app/agents/consolidate.py`
2. **Rewrite Company/Quant/Risk agents** — sliced input, dict-keyed output
3. **Update `app/graph/pipeline.py`** — replace static nodes with `.map()` pattern
4. **Update tests** — mock map iterations, verify merged state
5. **Integration test** — run graph with 3+ tickers, verify consolidated output

---

## Testing

| Test | Scope |
|------|-------|
| `tests/unit/test_company_agent_multi.py` | CompanyAgent with sliced state returns dict-keyed output |
| `tests/unit/test_quant_agent_multi.py` | QuantAgent with sliced state returns dict-keyed output |
| `tests/unit/test_risk_agent_multi.py` | RiskAgent reads per-ticker data, outputs dict-keyed |
| `tests/integration/test_graph_map_fanout.py` | Graph runs map nodes, merges correctly, consolidate executes |
| `tests/integration/test_consolidate_node.py` | Sector weights, concentration flags computed correctly |

---

## References

- LangGraph `map` pattern docs: https://langchain-ai.github.io/langgraph/how-tos/map-reduce/
- ADR-031: Multi-Ticker AgentState & Graph Architecture
- ADR-009: LangGraph Reducers (`merge_dicts`)
- `app/graph/pipeline.py` — current graph definition