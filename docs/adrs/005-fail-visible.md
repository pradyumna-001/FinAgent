# ADR 005: Fail Visible Principle

## Status
Accepted (2026-07-24)

## Context
Financial data sources fail: Tavily API down, yfinance rate limited, NVIDIA NIM timeout. Silent failures produce misleading morning notes.

Options:
1. **Fail fast** — Raise exception; pipeline stops; no output
2. **Fail silent** — Log error; continue with empty data; looks like success
3. **Fail visible** — Catch error, append `DataFlag` to state, continue; downstream sees flag and surfaces warning

## Decision
**Fail Visible** — Every agent catches exceptions, creates `DataFlag` with source/severity/message, appends to `state["flags"]`, sets output to `None`/empty, and returns. Pipeline continues. EditorAgent embeds explicit warnings in morning note text.

## DataFlag Schema
```python
@dataclass(frozen=True)
class DataFlag:
    source: str           # "tavily", "yfinance", "nvidia_nim", "risk_parse", "editor_parse"
    severity: Severity    # INFO, WARNING, FATAL
    message: str
    created_at: datetime  # auto-set
```

Severity semantics:
- **INFO**: Non-critical observation (e.g., "fallback model used")
- **WARNING**: Data degraded but pipeline continues (e.g., "company news unavailable")
- **FATAL**: Critical failure; section output is None (e.g., "Tavily API key invalid")

## Rationale
- **Trust** — Managers must know when data is missing; never deliver incomplete note without indication
- **Debugging** — Flags provide audit trail of what failed and when
- **Resilience** — Pipeline doesn't stop; partial output is better than no output
- **Compliance** — Financial advice requires transparency about data quality

## Consequences
- **Positive**: Transparent, auditable, resilient
- **Negative**: More complex state; EditorAgent must handle `None` outputs; confidence scores penalized
- **Testing**: Every integration test mocks failures and verifies `DataFlag` appears in output

## Implementation Notes
- `app/utils/flags.py` defines `DataFlag`, `Severity` enum
- All 5 agents follow pattern: `try/except` → `new_flags.append(DataFlag(...))` → return partial state
- `app/utils/editor_confidence.py::apply_confidence_penalties()` reduces confidence scores for flagged sections (< 0.5)
- EditorAgent prepends `⚠️ Aviso: ...` warnings to morning note text for flagged sections