# Issue #08 — MacroAgent implementation plan

**Branch:** `feature/issue-08-macro-agent` (keep #07 commits on it; all commits attributable to this issue)
**Date:** 2026-08-11
**Status:** approved, ready to execute

## Locked decisions

1. **Branch strategy** — keep current branch as-is. No separate PR for #07. All commits on `feature/issue-08-macro-agent` relate to #08.
2. **Missing-key behavior** — `DataFlag(severity=FATAL)` + return `state` with `macro_context=None`. No `RuntimeError`.
3. **Real-data smoke test** — deferred to end-of-session (Chunk 7). Not a CI test.
4. **`app/prompts/main.py` deletion** — ignored (leave unstaged, do not stage).
5. **`app/agents/__init__.py`** — user creates manually before Chunk 1 starts.
6. **LLM provider** — keep NVIDIA NIM (`app/services/llm.py`). Do NOT switch to OpenAI GPT-4o-mini. Update `docs/issues.md:197` to reflect this.

## Chunk sequence (each = one commit, tests green after each)

### Chunk 1 — Fix the unit tests (red→green first)
**Files:** `tests/unit/test_macro_agent.py`, `tests/unit/test_macro_agent_stub.py`

- Replace `patch("app.agents.macro.os.getenv", …)` → patch `app.core.config.settings.TAVILY_API_KEY` (or `app.agents.macro.settings.TAVILY_API_KEY`).
- Fix mock Tavily result key `excerpt` → `snippet` to match `app/agents/macro.py:37`.
- Fix `mock_client.get` → `mock_client.post` — agent does POST at `macro.py:22`.
- `test_macro_agent_no_key`: change expectation from `pytest.raises(RuntimeError)` to `DataFlag(FATAL)` in `state["flags"]` + `macro_context is None`. Matches Chunk 2 behavior.
- Run `pytest tests/unit/test_macro_agent.py tests/unit/test_macro_agent_stub.py -v` → green.

**Note:** Chunk 1 will be red until Chunk 2 lands (because `test_macro_agent_no_key` expects the new flag-and-return behavior, but `macro.py` still raises). Either:
- (a) Land Chunk 1+2 together as a single commit, OR
- (b) Split Chunk 1 into 1a (keep `pytest.raises(RuntimeError)`, just fix patches/keys/post) and 1b (after Chunk 2, update the no-key test to expect DataFlag).

**Chosen approach:** (a) — land Chunks 1+2 as one commit so tests stay green per the Socratic loop invariant.

### Chunk 2 — Refactor `macro.py` for Fail-Visible + TypedDict
**Files:** `app/agents/macro.py` (and stage `app/core/config.py`, `pyproject.toml`, `uv.lock` changes)

- Replace `raise RuntimeError("TAVILY_API_KEY missing")` at `macro.py:16` with:
  ```python
  state["flags"].append(DataFlag(source="tavily", severity=Severity.FATAL, message="TAVILY_API_KEY missing"))
  state["macro_context"] = None
  state["data_freshness"]["macro"] = datetime.utcnow()
  return state
  ```
- Replace plain `dict` at `macro.py:54–59` with `MacroOutput(headline=…, summary=…, sources=…, fetched_at=…)` TypedDict instantiation. Imports: `from app.graph.state import MacroOutput`.
- Stage the config/pyproject/uv.lock changes (they carry the openai/httpx deps backing `app/services/llm.py`).
- Run `pytest tests/unit/test_macro_agent*.py -v` → green.

### Chunk 3 — Structured logging with correlation IDs
**Files:** `app/agents/macro.py`, `tests/unit/test_macro_agent.py`

- Add module logger: `import logging; logger = logging.getLogger(__name__)`.
- Log at entry: `logger.info("macro_agent_start", extra={"pipeline_run_id": …, "morning_note_id": …, "manager_id": …})`.
- Log at each failure path: Tavily down, LLM None, success with headline.
- New unit test using `caplog` fixture: assert a log record with `pipeline_run_id` is emitted at start.
- Run tests → green.

### Chunk 4 — Tavily BR-specific sources
**Files:** `app/agents/macro.py`, `tests/unit/test_macro_agent.py`

- Bump `max_results` 5 → 10.
- Add `include_domains=["bcb.gov.br", "ibge.gov.br", "br.reuters.com", "bloomberg.com.br"]` to the POST payload.
- Update the test mock to assert `include_domains` was passed (inspect `client.post.call_args`).
- Run tests → green.

### Chunk 5 — Update `docs/issues.md`
**File:** `docs/issues.md`

- Line 197: change "Usar GPT-4o-mini para extração e resumo" → "Usar NVIDIA NIM (modelo primário + fallback) para extração e resumo".
- Mark items 1, 2, 5, 6, 7, 8, 9, 4 as ☑.
- Item 10 (real-data test) stays ☐ with a follow-up note: "Deferred to end-of-session via scripts/run_macro_agent.py".
- Visual check only — no test impact.

### Chunk 6 — Push + PR
**Action only.**

- `git push -u origin feature/issue-08-macro-agent` (fixes Rule 3 violation).
- Open PR per `junior-git-workflow` skill's PR template.
- Return PR URL.

### Chunk 7 — Journal entry + real-data smoke (end-of-session)
**Files:** `docs/journal/new/1_week/<date>-issue-08-macro-agent.md` (skill creates the dir)

- Load `junior-journal` skill, scaffold entry collaboratively.
- Run `python scripts/run_macro_agent.py` locally, capture printed output, save to the journal entry as evidence.
- Capture resume point in the journal entry itself (branch, last commit hash, what's next).

## Tavily field name — correction

Tavily's `/search` API returns `content` per result object (confirmed against
https://docs.tavily.com/documentation/api-reference/endpoint/search on 2026-08-11).
It does NOT return `snippet` or `excerpt`. The original `macro.py:37` reading
`top.get('snippet', '')` was a real bug — it would always fall back to empty
string against the live API.

**Correction applied:**
- `macro.py` Pass 3 → use `top.get('content', '')` everywhere `snippet` appeared.
- `tests/unit/test_macro_agent.py` mocks → use `"content": "..."` (not `excerpt`, not `snippet`).
- LLM-None fallback path → use `top.get('content', '')` for the raw-summary fallback.

This bug would have shown up at Chunk 7's real-data smoke test. Catching it now
means Chunk 7 will actually validate end-to-end behavior against the live API.

## Loose ends

- `app/agents/__init__.py` — user creates before Chunk 1 starts.
- `docs/journal/new/1_week/` dir doesn't exist yet — `junior-journal` skill creates at write time.
- `app/prompts/main.py` deletion — ignored, never staged.
- `uv.lock` / `pyproject.toml` / `app/core/config.py` changes — staged with Chunk 2 (carry NVIDIA settings + openai dep).

## Verification gates

After every chunk: `pytest tests/unit/ -v` must be green (no broken window).
After Chunk 6: PR open, branch pushed.
After Chunk 7: journal entry committed, resume point captured.

## Open follow-ups after #08 closes

- Real-data test result recorded in journal (evidence for checklist item 10).
- Tavily `include_domains` accuracy vs. actual Tavily support — verify against Tavily docs during Chunk 4 (Tavily does support `include_domains` per their API, but worth confirming).
- `mypy app` clean run — the current `[[tool.mypy.overrides]]` block ignores `app.core.config`, that's fine for #08 but worth keeping in mind.
