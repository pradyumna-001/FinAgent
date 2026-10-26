# Issue #14 — Technical Overview & Learning Plan

**Issue:** #14 LangGraph StateGraph Completo  
**Branch:** `feature/issue-14-langgraph` (already exists)  
**Goal:** Build the complete LangGraph pipeline: MacroAgent → [CompanyAgent, QuantAgent] parallel → RiskAgent → EditorAgent with Postgres checkpointer, state validation, and LangSmith tracing.

---

## 1. New Concepts You'll Encounter

### 1.1 LangGraph StateGraph
**What it is:** A directed graph where nodes are async functions (`AgentState → AgentState`) and edges define execution order. Supports parallel fan-out/fan-in.

**Key classes:**
- `StateGraph[StateType]` — the graph builder
- `START`, `END` — special nodes
- `add_node(name, callable)` — register a node
- `add_edge(from_node, to_node)` — sequential edge
- `add_conditional_edges(...)` — branching (not needed here)
- `compile(checkpointer=...)` — produces runnable `CompiledGraph`

**Documentation:**
- https://langchain-ai.github.io/langgraph/how-tos/create-graph/
- https://langchain-ai.github.io/langgraph/concepts/low_level/

### 1.2 PostgresSaver (Checkpointer)
**What it is:** Persists graph state to PostgreSQL after each node. Enables resume, debugging, and human-in-the-loop.

**Key class:** `PostgresSaver.from_conn_string(async_dsn)` — uses `asyncpg` driver.

**Integration:** Pass to `graph.compile(checkpointer=saver)`. Then invoke with `config={"configurable": {"thread_id": "unique-run-id"}}`.

**Documentation:**
- https://langchain-ai.github.io/langgraph/reference/checkpointers/#langgraph.checkpoint.postgres.aio.AsyncPostgresSaver
- https://langchain-ai.github.io/langgraph/concepts/persistence/

### 1.3 LangSmith Tracing (Tags)
**What it is:** Observability platform. Tags are key:value pairs attached to every trace for filtering.

**How to add:** Pass `tags=[...]` in the `config` dict when invoking `graph.ainvoke(state, config=config)`.

**Required tags per spec:**
```
gestor_id:{manager_id}
empresa:{company_ticker}
data:{YYYY-MM-DD}
pipeline_run_id:{uuid}
morning_note_id:{uuid}
```a

**Documentation:**
- https://docs.smith.langchain.com/concepts/tracing
- https://docs.smith.langchain.com/how_to_guides/tracing/tag_runs

### 1.4 Parallel Execution in LangGraph
**Pattern:** Fan-out from one node to multiple nodes, then fan-in to a single node.

```
macro → company
   ↘
    → quant
       ↗
      risk
```

**Implementation:** Two `add_edge("macro", "company")` and `add_edge("macro", "quant")`, then two `add_edge("company", "risk")` and `add_edge("quant", "risk")`. LangGraph handles the join automatically — `risk` runs once when both predecessors complete.

**Documentation:**
- https://langchain-ai.github.io/langgraph/how-tos/branching/

---

## 2. Existing Code You'll Connect

| File | What It Provides |
|------|------------------|
| `app/graph/state.py` | `AgentState` (TypedDict), `create_initial_state()`, `validate_state()` |
| `app/agents/macro.py` | `macro_agent_node(state) → AgentState` |
| `app/agents/company.py` | `company_agent_node(state) → AgentState` |
| `app/agents/quant.py` | `quant_agent_node(state) → AgentState` |
| `app/agents/risk.py` | `risk_agent_node(state) → AgentState` |
| `app/agents/editor.py` | `editor_agent_node(state) → AgentState` |
| `app/db/session.py` | `engine` (async SQLAlchemy engine) for checkpointer DSN |
| `app/core/config.py` | `settings.DATABASE_URL` |

**All 5 agent nodes already exist and follow the same contract:**  
`async def agent_node(state: AgentState) -> AgentState` — never raises, appends `DataFlag` on failure.

---

## 3. Files to Create (Boilerplate Plan)

### 3.1 `app/graph/pipeline.py` — The Graph Definition

**Structure (you will type this in chunks):**

1. **Imports** — LangGraph classes, checkpointer, engine, state utilities, all 5 agent nodes
2. **Validation wrapper** — `validated_node(node_fn, name)` that calls `validate_state(state)` before delegating to the agent node
3. **Graph builder** — `StateGraph(AgentState)` instance
4. **Add 5 nodes** — each wrapped: `builder.add_node("macro", validated_node(macro_agent_node, "macro"))`, etc.
5. **Add edges** — sequential: `START → macro`; parallel fan-out: `macro → company` and `macro → quant`; parallel fan-in: `company → risk` and `quant → risk`; sequential: `risk → editor → END`
6. **Compile with checkpointer** — `AsyncPostgresSaver.from_conn_string(str(engine.url))` passed to `builder.compile(checkpointer=saver)`
7. **Export** — `__all__ = ["graph", "create_initial_state"]`

### 3.2 `scripts/run_pipeline.py` — Terminal Test Script

**Structure (pattern from `run_macro_agent.py` — you will type this):**

1. **Imports** — `asyncio`, `datetime`, `UTC`, `pprint`, `graph` and `create_initial_state` from `app.graph.pipeline`
2. **`main()` async function** — creates initial state with `manager_id=1`, `company_ticker="PETR4"`, unique run/note IDs
3. **Config dict** — `configurable.thread_id = pipeline_run_id`, `tags` list with 5 required tags (gestor_id, empresa, data, pipeline_run_id, morning_note_id)
4. **Invoke** — `await graph.ainvoke(state, config=config)`
5. **Print results** — morning_note, recommendation, confidence_scores, flags
6. **Entry point** — `if __name__ == "__main__": asyncio.run(main())`

---

## 4. Dependencies to Add (via `uv add`)

| Package | Purpose |
|---------|---------|
| `langgraph` | Core graph framework |
| `langgraph-checkpoint-postgres` | PostgresSaver |
| `langsmith` | Tracing (optional, for local dev) |

Add to `pyproject.toml` dependencies array:
- `"langgraph>=0.2.0"`
- `"langgraph-checkpoint-postgres>=1.0.0"`

---

## 5. Verification Checklist

After implementation, verify:

- [ ] `uv run python scripts/run_pipeline.py` executes without error
- [ ] Output shows `morning_note` (string), `recommendation` (dict), `confidence_scores` (dict with 5 keys), `flags` (list)
- [ ] LangSmith dashboard shows trace with 5 tags
- [ ] Postgres `checkpoints` table has a row for the run
- [ ] `pytest tests/` passes (no new test files needed for #14; #15 adds tests)

---

## 6. Learning Resources (Prioritized)

| Priority | Resource | Time |
|----------|----------|------|
| 1 | LangGraph "Create a Graph" tutorial | 20 min |
| 2 | LangGraph "Persistence with Postgres" guide | 15 min |
| 3 | LangGraph "Parallel Execution" how-to | 10 min |
| 4 | LangSmith "Tagging Runs" guide | 5 min |

---

## 7. Questions to Answer Before Coding

1. **Where does the checkpointer DSN come from?** → `app/db/session.py:engine.url` (already async)
2. **How does `validate_state()` integrate?** → Wrapper around each node (shown in boilerplate)
3. **How do parallel edges work?** → Two edges from same source, two edges to same target; LangGraph joins automatically
4. **What `thread_id` to use?** → `pipeline_run_id` from state (unique per run)
5. **Where do tags go?** → In `config={"tags": [...], "configurable": {"thread_id": ...}}` at invoke time

---

## 8. Next Steps

1. **You confirm this plan** — ask questions if anything is unclear
2. **Install dependencies** — `uv add langgraph langgraph-checkpoint-postgres`
3. **Start Socratic implementation** — Chunk 1: `app/graph/pipeline.py` imports + validation wrapper
4. **Verify after each chunk** — run import test, then graph compile test, then full script

Ready to proceed with Chunk 1?