# Follow-up: MacroAgent audit — agent code + test suite

Filed during #09 CompanyAgent work (session 2026-08-12) when Prady asked: "is macro actually perfect? maybe we should make it better."

Audit covers `app/agents/macro.py` (97 lines) and `tests/unit/test_macro_agent.py` (121 lines), cross-referenced against the contracts we just locked in #09 CompanyAgent (`app/agents/company.py`, `app/prompts/company.py`, `tests/unit/test_company_agent*.py`).

## Summary

**Macro has 6 distinct issues** — 2 are real bugs (one in agent code, one in tests), 4 are thin/shallow patterns that should match the company standard. None are pipeline-breaking; all are quality regressions vs the #09 work.

## Issues (sorted by severity)

### 1. **BUG (agent code + test) — `source="tavily"` for LLM failure (HIGH)**

**Location:** `app/agents/macro.py:78–85` (agent code) and `tests/unit/test_macro_agent.py:107` (test assertion).

In `macro.py`, the LLM-None branch (`if summary is None:`) constructs a `DataFlag` with `source="tavily"`. That's wrong: the LLM (NVIDIA NIM) failed, not Tavily. Tavily succeeded — it returned the data we asked for. The flag source should be `"nvidia_nim"`, exactly as we locked in `company.py`.

The test at `test_macro_agent.py:107` asserts `flag.source == "tavily"` — it was written against the buggy agent code, so the assertion *passes* but the contract is wrong. Fixing the agent code without fixing the test would make the test fail; both must be fixed together.

**Why it matters:** downstream `RiskAgent` (#12) and operator triage both depend on the `source` field to know *which upstream* failed. A mislabeled source sends the operator to file a ticket against Tavily when they should be filing one against NVIDIA NIM (or our LLM call site).

**Fix:** `app/agents/macro.py:81` change `source="tavily"` → `source="nvidia_nim"`. `tests/unit/test_macro_agent.py:107` change `assert flag.source == "tavily"` → `assert flag.source == "nvidia_nim"`. Done.

---

### 2. **BUG (test) — `test_macro_agent_tavily_failure` asserts shallow FATAL/WARNING contract (MEDIUM)**

**Location:** `tests/unit/test_macro_agent.py:68–72`.

The HTTP-failure test only asserts:
- `result["macro_context"] is None` ✓
- `flag.source == "tavily"` ✓
- `isinstance(result["data_freshness"]["macro"], datetime)` ✓

It never asserts `flag.severity == Severity.WARNING`. Compare to the company tests, which explicitly assert `Severity.FATAL` on the no-key test and on the all-null-fields test. If a regression changes the HTTP-failure branch from `WARNING` to `FATAL` (or to `INFO`), this test passes silently.

**Fix:** import `Severity` (already imported via `DataFlag` chain — confirm) and add `assert flag.severity == Severity.WARNING` after the existing `flag.source` assertion.

---

### 3. **LATENT BUG (agent code) — parse block has no try/except validator (HIGH)**

**Location:** `app/agents/macro.py:65–93`.

Same latent bug we discovered and fixed in #09 `company.py`: the `if data and data.get("results"):` block does unconditional `top.get(...)` and ships garbage to `summarize()` if Tavily returns `{"results": [{"title": null, "content": null}]}`. No `ValueError` is raised; the LLM gets `"\n\n\n"` or `"None\n\nNone\nNone"`, returns garbage, and the morning note ships garbage with no flag.

We just redesigned this for company: a validator gate (`if not (top.get("title") and top.get("content")):`) wrapped in `try/except (ValueError, KeyError, IndexError)` → `FATAL` `DataFlag(source="tavily", message=f"parse-block failed for {ticker}: {exc}")`. The macro version needs the identical refactor.

Note: macro doesn't have a `company_ticker` state field. The message format should be `f"parse-block failed: {exc}"` (no ticker) — since there's only one "Brazil macro" query per pipeline run, the ticker isn't needed for routing.

**Fix:** backport the company.py fix-chunk we just wrote (lines 76–) to macro.py, dropping the ticker interpolation. Add an all-null-fields test (`test_macro_agent_all_null_fields`) mirroring `test_company_agent_all_null_fields`.

---

### 4. **STYLE (prompts module) — `MACRO_PROMPTS.build_user_prompt` lacks the company improvements (MEDIUM)**

**Location:** `app/prompts/macro.py:8–12`.

`company.py`'s `build_user_prompt` was written yesterday with three improvements over macro:
- **(a) f-string instead of `+` concatenation:** `f"Summarize...{raw_text}"` instead of `"... :\n\n" + raw_text`.
- **(b) Docstring with `Args`/`Returns`/`Raises`.**
- **(c) `if not raw_text: raise ValueError(...)` guard clause.**

Macro has none of these. The `+` concatenation is benign; the missing docstring is a docs gap; the missing `ValueError` guard means the macro parse-block fix-chunk (#3 above) can't exist — we need the prompt to raise on empty raw_text so the parse-block `try/except` catches something.

**Fix:** backport all three improvements from `app/prompts/company.py` to `app/prompts/macro.py`. Specifically:
- Add `if not raw_text: raise ValueError("raw_text must be non-empty")` at the top of `build_user_prompt`.
- Convert `+` to f-string.
- Add docstring matching `company.py`'s shape.

Update `"3-5 sentences"` → macro can keep `"concise paragraph"` (different output shape — macro is a paragraph, company is event bullets) OR standardize on the more specific form. That's an editorial call, not a code-correctness one.

---

### 5. **STYLE (test) — `make_state()` helper vs inline `create_initial_state(...)` (LOW)**

**Location:** `tests/unit/test_macro_agent.py:10–16`.

Macro uses a local `make_state()` helper at module scope; company inlines `create_initial_state(manager_id=1, company_ticker="PETR4", pipeline_run_id=..., morning_note_id=...)` per test. Both work. Macro is more DRY (single edit point); company is more grep-able (search finds each test).

This is a judgment call, not a bug. Pick one and standardize across both macro and company test files.

**Fix:** decision call. Recommendation: keep `make_state()` helper — it's the smaller diff (macro stays, company refactors). Or keep inline (macro refactors to inline) if grep-ability wins. Either way, *both files should match*.

---

### 6. **STYLE (test) — `flag.source == "tavily"` assertion in `test_macro_agent_tavily_failure` (LOW)**

**Location:** `tests/unit/test_macro_agent.py:71`.

The HTTP-failure test correctly asserts `flag.source == "tavily"` — that's fine (Tavily did fail). But it doesn't assert `flag.severity` (issue #2 above). This is mostly a sub-point of #2 — calling out separately so the fix PR covers both in one pass.

Also: the HTTP-failure branch sets `severity=Severity.WARNING`. The test should explicitly assert that — not just `isinstance(flag, DataFlag)`. Same fix as #2.

---

## What is NOT a bug

- `datetime.now(UTC)` instead of deprecated `utcnow()` — already fixed in #08 (yesterday's issue). Good.
- `httpx.AsyncClient(timeout=10.0)` pattern — matches company. Good.
- `include_domains` filter on Tavily query — already added in #08. Good.
- `MacroOutput` TypedDict — already in #08. Good.
- Correlation-ID entry logger (`extra={pipeline_run_id, morning_note_id, manager_id}`) — already in #08. Good.
- The `summarize` `None`-fallback to raw content — semantic is right, only the `source` field is mislabeled (issue #1 above).

## Why not fixed in #09 PR

Scoping discipline: #09 is CompanyAgent. #08 (macro) closed yesterday with a green suite — but the audit wasn't part of #08's exit criteria. Filing this as a separate issue keeps the PR scope clean.

## Scope of the follow-up PR

Minimum viable fix (bug + critical latent):
1. `app/agents/macro.py:81` — `source="tavily"` → `source="nvidia_nim"` (issue #1).
2. `tests/unit/test_macro_agent.py:107` — `assert flag.source == "tavily"` → `"nvidia_nim"` (issue #1).
3. Backport company.py parse-block fix-chunk to `app/agents/macro.py:65–93` — validator + try/except + FATAL flag (issue #3).
4. Add `test_macro_agent_all_null_fields` test mirroring `test_company_agent_all_null_fields` (issue #3).
5. Backport company.py `build_user_prompt` improvements to `app/prompts/macro.py` — ValueError guard, f-string, docstring (issue #4).

Polish pass (low-priority):
6. `tests/unit/test_macro_agent.py:71` — add `assert flag.severity == Severity.WARNING` (issues #2 + #6).
7. Standardize `make_state()` helper vs inline `create_initial_state(...)` across macro + company test files (issue #5).

## Suggested branch
`fix/issue-08b-macro-audit-fixes`

## Suggested priority
- **Issues #1, #3, #4** (bug + latent + dependency): HIGH — file before #12 RiskAgent work starts (RiskAgent consumes `flag.source`, will inherit the mislabel bug).
- **Issue #2** (shallow FATAL/WARNING assertion): MEDIUM — quality, not pipeline-affecting.
- **Issues #5, #6** (style standardization): LOW — cleanup, no user impact.

## Found by
Session 2026-08-12, issue #09 work. Prady asked "is macro actually perfect?" after we audited company tests against macro's precedent. The audit surfaced 6 issues; Socratic protocol on "macro's source='tavily' for LLM" revealed the test bug; deeper read of `macro.py` parse block revealed the latent bug (same root cause as company's, not yet fixed); comparison to `app/prompts/company.py` revealed the prompt-module regressions.
