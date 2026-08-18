# Plan — Issue #09 CompanyAgent (safety + execution protocol)

**Goal:** Implement `app/agents/company.py` → `company_agent_node(state: AgentState) -> AgentState` that queries Tavily for B3 company news by ticker, extracts `CompanyEvent`s via NVIDIA NIM (primary + fallback), and updates `AgentState` in-place. Fail-visible. Never raises.
**GitHub issue:** #60 (label: enhancement)
**Branch:** `feature/issue-09-company-agent` — clean tip off `main`, reset is done.

---

## 1. Non-negotiables (invariants, not preferences)

- **Fail-visible:** Any Tavily HTTP error, JSON parse error, or LLM `None` returns → `state["flags"].append(DataFlag(...))`. The node MUST still set `state["data_freshness"]["company"]` and return `state`. Never `raise` out of the function boundary.
- **Mutate, don't reconstruct:** Return the same `state` object (LangGraph shared-state contract). Do NOT call `create_initial_state` inside the node.
- **Typed output:** `state["company_events"]` is `list[CompanyEvent]` (per `app/graph/state.py:14`). Each `CompanyEvent` is a TypedDict with `title`, `date`, `source`, `summary` — all `str`.
- **No mixed responsibilities:** CompanyAgent never computes quant metrics and never emits a `Recommendation` (those belong to #10/#13 respectively).
- **Correlation logging:** Every `logger.info(...)` includes `pipeline_run_id`, `morning_note_id`, `manager_id` from state (mirror `app/agents/macro.py:20-27`).
- **Freshness always written:** `state["data_freshness"]["company"]` is set on every exit path — success, Tavily failure, and LLM failure.
- **Key precedence rule to remember:** Write `state["data_freshness"]["company"] = datetime.now(UTC)` — NOT `datetime.now()` (naive). The macro agent already uses `datetime.now(UTC)`; we match it.

## 2. Reuse inventory (DO NOT re-implement)

| Reuse | Where | Why |
|---|---|---|
| `DataFlag`, `Severity` | `app/utils/flags.py` | Same enum and frozen dataclass |
| `summarize(system, user)` | `app/services/llm.py:17` | Has primary→fallback model logic already |
| `create_initial_state`, `CompanyEvent`, `AgentState` | `app/graph/state.py:14,44` | TypedDict shape already defined |
| `httpx.AsyncClient` with `timeout=10.0` | `app/agents/macro.py:45` | Pattern: `async with` + `raise_for_status` |
| Prompt file pattern `app/prompts/macro.py` | mirror as `app/prompts/company.py` | Single source of truth for prompt strings |
| Test pattern `tests/unit/test_macro_agent.py` | mirror as `tests/unit/test_company_agent.py` | `patch(...httpx.AsyncClient, ...)`, `patch(...summarize, ...)` |
| Stub test pattern `tests/unit/test_macro_agent_stub.py` | mirror as `tests/unit/test_company_agent_stub.py` | Tests the no-key / FATAL-DataFlag path without HTTP |

## 3. Failure-handling decision matrix (which DataFlag severity)

| Failure | Severity | Source string | Rationale |
|---|---|---|---|
| `TAVILY_API_KEY` missing / empty | `FATAL` | `"tavily"` | Can't run at all — downstream RiskAgent must surface this. Matches macro.py:34. |
| Tavily HTTP/network error | `WARNING` | `"tavily"` | Transient; pipeline can proceed with `company_events=[]`. Matches macro.py:57. |
| Tavily returned but zero results | (no flag, empty list) | — | No failure — nothing to extract. |
| LLM `summarize` returns `None` | `WARNING` | `"nvidia_nim"` | Failing upstream is the LLM, not Tavily. Fall back to raw content. Matches macro.py:79-86 in shape, differs in source string (per decision). |
| Tavily domain whitelist | `include_domains` payload arg | — | `cvm.gov.br`, `infomoney.com.br`, `globo.com/valor-economico` (or `valor-economico.com.br` per docs). |

## 4. Chunk breakdown (each ≤25 lines, each verified)

| # | Scope | File | Verification |
|---|---|---|---|
| C1 | Module shell: imports, logger, function signature + docstring + `logger.info` entry guard. No business logic. | `app/agents/company.py` | `python -c "from app.agents.company import company_agent_node"` imports cleanly. |
| C2 | Tavily key-missing branch: FATAL DataFlag + `state["data_freshness"]["company"]` + early return. | same | Stub test (mirror `test_macro_agent_stub.py`) passes. |
| C3 | Tavily HTTP call with `include_domains` for B3 sources + `except` → WARNING DataFlag. | same | Stub test for network failure passes. |
| C4 | Build `raw_text`, call `summarize(...)`, handle `None` → WARNING + raw fallback. | same | Unit test `test_company_agent_llm_none` passes. |
| C5 | Build `CompanyEvent` list and write `state["company_events"]` + `state["data_freshness"]["company"]`. | same | Happy-path unit test passes (mirror of `test_macro_agent_happy_path`). |
| C6 | Prompt module `app/prompts/company.py` (mirrors `app/prompts/macro.py`). | new file | Importable. |
| C7 | Log entry test (mirror of `test_macro_agent_logs_entry`) for correlation IDs. | `tests/unit/test_company_agent.py` | `pytest tests/unit/test_company_agent.py -v` green. |
| C8 | Lint + typecheck + full unit suite green. | n/a | `ruff check .`, `mypy app`, `pytest tests/unit/ -v`. |

## 5. Behaviors explicitly off-limits in this issue

- Quantitative calculations (P/L, EV/EBITDA) → issue #10.
- Resident memory graphs (MAGMA) → issue #17.
- Recommendation generation → issue #13 (EditorAgent).
- DB writes — agents return state, the graph/celery worker persists. (#20.)
- RLS — handled by the request middleware (`SET LOCAL app.manager_id`), not by the agent.

## 6. Socratic protocol

- After every chunk: 3 WHY questions (structural concept / architectural reason / debugging-operator perspective) before the next chunk.
- If a guessed answer is shallow (e.g., "so it works"), push back for a precise reason.
- Verify with a **fast scratch check** (≤8 lines) that proves ONE invariant per chunk.
- After chunks C1–C3 (entry guard + key + HTTP), summarize what we covered and what's next.

## 7. Git safety

- Do NOT stage `uv.lock`, `.opencode/`, `.pr_body*.md`, or `3-month-plan.md` (all stay untracked or stashed per user instruction).
- Commit only when the user explicitly asks. Skill rule: "NEVER commit changes unless the user explicitly asks."
- When the user is ready to commit, load `junior-git-workflow` skill for per-issue-branch + Socratic-commit-loop rules.
- One commit per verified chunk (atomic), message shape: `feat(issue-09): <chunk scope>`.

## 8. Hazards the skill flags (anti-patterns to watch for)

- `state.get("company_events" or [])` — wrong; this is `state.get("company_events") or []` if we ever read. But we WRITE: `state["company_events"] = […]` directly. Insist on the distinction.
- `datetime.now()` (naive) vs `datetime.now(UTC)` — use UTC.
- `state["flags"].append(DataFlag(source="company", ...))` — the `source` should reflect the failing upstream (`"tavily"` for HTTP, `"nvidia_nim"` for LLM), not the agent name. Matches MacroAgent using `source="tavily"`.
- Comments inside `company.py` explaining `self`, `state`, etc. — those belong in chat, not in production code.
- Docstring typos: do a `Opetional` / `Pulic` / `caus` / `empres` sweep before commit.

## 9. Exit criteria (issue #09 = done)

- [ ] `app/agents/company.py` exists with `company_agent_node`.
- [ ] `app/prompts/company.py` exists (with C6 improvements: f-string, docstring, guard clause).
- [ ] `tests/unit/test_company_agent.py` and `tests/unit/test_company_agent_stub.py` green.
- [ ] `ruff check .` clean.
- [ ] `mypy app` clean.
- [ ] All 4 invariant tests in plan tasks satisfied.
- [ ] Commit(s) pushed (only if user asks).
- [ ] PR opened against `main` (only if user asks, via `junior-git-workflow` skill).
- [ ] PR body mentions `app/prompts/macro.py` refactor as a follow-up (f-string, docstring, guard clause — same improvements we made to company.py).

## Follow-ups (not in this issue's scope)

- Refactor `app/prompts/macro.py` to match `app/prompts/company.py` quality (f-string, docstring, guard clause). Tracked in PR body when issue #09 ships.

## 10. When to escalate / pivot

If the user stops answering the Socratic questions for 2 chunks in a row, ask what they want now (more examples / less theory / finished file) — per skill rules.

## 11. Resume point (session 2026-08-11 → next session)

- Branch: `feature/issue-09-company-agent` at `8f99110` (no commits; all work uncommitted).
- GitHub issue #60 OPEN.
- Chunks C1–C6 complete. 4 unit tests green.
- **Pending fix-chunk (pre-C7):** wrap the parse block (`if data and data.get("results"):` body) in `try/except ValueError` → `FATAL` `DataFlag`. Latent bug surfaced in C6's Q3 Socratic question.
- After fix-chunk: C7 (log-entry test), C8 (lint/typecheck/full suite).
- Open Socratic question from end-of-session: "what two pieces of info should the FATAL `DataFlag.message` carry so the operator can decide codebase-bug vs Tavily-schema-bug?" — answer together at next session start.
- See `docs/journal/new/1_week/16.md` (appended #09 section) for full session record.
