# Follow-up: Extract TavilyService — deduplicate HTTP + parse + source-string discipline

Filed during #09 CompanyAgent work (session 2026-08-12) just before the PR went up for review. Prady asked: "does it make sense to create a future issue to develop a tavily service module?" — the answer was yes, after surfacing two real architectural tensions.

## Why now

Two call sites today (`app/agents/macro.py`, `app/agents/company.py`) already duplicate:
- `httpx.AsyncClient(timeout=10.0)` context manager.
- `client.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {tavily_key}"}, json=payload)`.
- `except Exception as exc:` → `WARNING` `DataFlag(source="tavily", message=f"Tavily request error: {exc}")`.
- `if not tavily_key:` → `FATAL` `DataFlag(source="tavily", message="TAVILY_API_KEY missing")` guard.
- The parse-block guard we just added in #09 (`try/except (ValueError, KeyError, IndexError)` → `FATAL`), soon to be backported to `macro.py` per issue #61.

Future agents `risk_agent` (#12), `quant_agent` (#13) will need news/event data — more duplication.

## Two architectural tensions this resolves

### 1. Source-string discipline
Today, `source="tavily"` vs `source="nvidia_nim"` lives in each agent's local code. We already found `macro.py` uses `source="tavily"` for LLM-None failures — a mislabel (filed in #61). A `TavilyService.search()` that returns `(results, error_flag)` centralizes "Tavily succeeded/failed"; the caller attaches LLM-specific `source="nvidia_nim"` only when the LLM fails. The bug class disappears.

### 2. Parse-block guard
The `try/except (ValueError, KeyError, IndexError)` → `FATAL` guard we just added to `company.py` (lines 76–) needs backporting to `macro.py` per #61. Next week `risk.py` will need the same. A service that returns *typed* `TavilyResult` (`results: list[TavilyArticle]`, `error: DataFlag | None`) instead of raw dicts pushes the guard *inside* the service. Agents stop touching `dict.get("title")` and receive `article.title: str | None`.

## Proposed shape

```python
# app/services/tavily.py
from dataclasses import dataclass
from app.utils.flags import DataFlag, Severity

@dataclass(frozen=True)
class TavilyArticle:
    title: str | None
    content: str | None
    url: str | None

@dataclass(frozen=True)
class TavilyResult:
    articles: list[TavilyArticle]
    error: DataFlag | None  # non-None if HTTP/parse/key failed

class TavilyService:
    def __init__(self, api_key: str, timeout: float = 10.0) -> None: ...
    async def search(
        self,
        query: str,
        include_domains: list[str],
        max_results: int = 10,
    ) -> TavilyResult: ...
```

### Rewrite of `company_agent_node` call site (sketch)

```python
tavily = TavilyService(api_key=settings.TAVILY_API_KEY)
if not tavily.api_key:
    state["flags"].append(DataFlag(source="tavily", severity=FATAL, message="TAVILY_API_KEY missing"))
    state["company_events"] = []
    state["data_freshness"]["company"] = datetime.now(UTC)
    return state

result = await tavily.search(
    query=f"{ticker} news Brazil",
    include_domains=["cvm.gov.br", "infomoney.com.br", "globo.com/valor-economico"],
    max_results=10,
)
if result.error:
    state["flags"].append(result.error)
    state["company_events"] = []
    state["data_freshness"]["company"] = datetime.now(UTC)
    return state

top = result.articles[0]
raw_text = f"{top.title or ''}\n\n{top.content or ''}\n{top.url or ''}"
# parse-block try/except no longer needed — service returned typed articles
summary = await summarize(system=COMPANY_PROMPTS.system, user=COMPANY_PROMPTS.build_user_prompt(raw_text=raw_text))
...
```

Notes:
- The `if not tavily.api_key` guard could move *inside* `TavilyService.__init__` and `search()` returns `TavilyResult(articles=[], error=FATAL_flag)` — but that hides the missing-key check behind a method call. Keeping the explicit guard in the agent keeps the contract visible at the boundary. The shape decision is open for debate in the issue.
- `TavilyArticle.title` is `str | None`. The agent still does `.title or ''` for the f-string — but `top.title` is now a typed field, not a dict access; the `.get("title")` and dict-shape-question-marks disappear.
- The `summarize-is-None` branch stays in the agent (LLM failure is agent responsibility, not service responsibility). The `source="nvidia_nim"` flag stays correct.

## Scope of the refactor PR

1. New file `app/services/tavily.py` with `TavilyArticle`, `TavilyResult`, `TavilyService`.
2. Unit tests for `TavilyService.search()`:
   - happy path returns typed articles;
   - HTTP failure returns `error: DataFlag(source="tavily", severity=WARNING)`;
   - all-null-fields response returns `error: DataFlag(source="tavily", severity=FATAL)` with disambiguating message;
   - empty key handled (either in `__init__` or in `search` — design call).
3. Rewrite `app/agents/macro.py` to use `TavilyService`. Drop local httpx boilerplate. Delete the parse-block try/except (service owns it). Keep LLM-None branch + `source="nvidia_nim"` flag.
4. Rewrite `app/agents/company.py` to use `TavilyService`. Same deletions as macro.
5. Update existing unit tests (`test_macro_agent.py`, `test_company_agent*.py`) to mock `TavilyService.search()` instead of `httpx.AsyncClient`. Tests get simpler — no `mock_client.__aenter__.return_value = mock_client` plumbing.
6. Update `scripts/run_macro_agent.py` and `scripts/run_company_agent.py` (after sys.path fix per current session) — unaffected by the refactor (they call `macro_agent_node` / `company_agent_node`, not the service directly).

## Suggested branch
`refactor/extract-tavily-service`

## Suggested priority
- **HIGH** if #12 RiskAgent needs Tavily data (likely — risk flags need news context). Risk should consume `TavilyService` directly, not duplicate the macro/company pattern a third time.
- **MEDIUM** if #12 doesn't need Tavily. Still valuable — deduplicates macro/company, removes the source-string bug class — but not blocking.

## Coordinated issues
- **#61 (macro audit)**: fix the `source="tavily"` mislabel + backport the parse-block guard. Best to do #61 *before* this refactor: #61 fixes the existing pattern in-place; this refactor extracts the pattern. If we do this refactor first, #61 becomes "delete the lines we just wrote and call the service" — wastes the #61 work.
- **#09 CompanyAgent**: ships as-is with the FATAL guard inline. Refactor follows.

## Found by
Session 2026-08-12, issue #09 work, just before session wrap. Prady asked the architectural question unprompted — Socratic protocol: surface real tensions, then ask the user to defend the abstraction shape rather than default to "yes, file it."
