# ADR 027: CORS Configuration and Allowed Origins

## Status
Accepted

## Context
The browser frontend (`FinAgent-Frontend`) consumes the FastAPI backend via `fetch`/TanStack Query from a different origin (Vite dev server `localhost:5173` in dev, a deployed origin in prod). Prior to this ADR the backend had no CORS middleware, so any browser request from the frontend origin was blocked by the same-origin policy. This ADR is the transport-layer enabler for Frontend issues #1 (`useFeedback` hook) and #2 (`FeedbackModal`); the API contract they consume (ADR-025) was already merged in PR #106.

## Decision
Apply Starlette `CORSMiddleware` via `app.add_middleware()` with:

- `allow_origins` sourced from env (`CORS_ALLOW_ORIGINS`, a JSON array string), with dev defaults `http://localhost:5173` and `http://127.0.0.1:5173`. Never hardcoded; never `["*"]`.
- `allow_credentials=True` — required for the JWT `Authorization: Bearer` flow. Credentials travel in the request header, and the browser must treat the request as credentialed.
- Explicit `allow_methods` (`GET`, `POST`, `PUT`, `DELETE`, `OPTIONS`, `PATCH`) — no blanket wildcard.
- Explicit `allow_headers` (`Authorization`, `Content-Type`, `X-Pipeline-Run-Id`, `X-Morning-Note-Id`) — the JWT bearer header plus the pipeline correlation headers the frontend sends.

## Consequences

### Positive
- Frontend can call the API end-to-end from the browser in dev and prod.
- Preflight (`OPTIONS`) handled by `CORSMiddleware`, so bearer-authenticated requests work.
- Security posture: explicit allow-list of origins/methods/headers, auditable and env-gated.

### Negative
- Every new frontend origin must be added to `CORS_ALLOW_ORIGINS` before it can call the API.
- CORS does **not** protect the server from non-browser clients (e.g. `curl`); auth must remain enforced at the API layer.

### Neutral
- `/health` is reachable cross-origin (no origin exception decision needed beyond the shared policy). A frontend liveness probe can hit it like any other route.
- `allow_origins=["*"]` + `allow_credentials=True` is rejected by Starlette — by design, and deliberately not used.

## Options Considered

### Option A: Explicit Origins from Env (Chosen)
`CORS_ALLOW_ORIGINS` JSON array, dev defaults to the two Vite origins; prod set via environment.

**Pros**: No wildcard with credentials, env-gated, auditable, blocks CSRF-style cross-origin reads
**Cons**: Deploy-specific origins must be configured

### Option B: Wildcard Origins
`allow_origins=["*"]` with `allow_credentials=True`.

**Pros**: Trivial, works for any origin
**Cons**: Forbidden by Starlette + the CORS spec when combined with credentials; would let any site read credentialed responses. Not viable for the bearer-token flow.

### Option C: Wildcard Methods/Headers Only
Explicit origins but `allow_methods=["*"]` / `allow_headers=["*"]`.

**Pros**: Less config churn as methods/headers evolve
**Cons**: Loser security posture; explicit list documents exactly what the frontend is permitted to send. Rejected in favor of explicitness for headers too (header `*` is legal with credentials but intentionally avoided).

## Compliance
- [x] Backend: `CORSMiddleware` in `app/main.py` via `app.add_middleware()`
- [x] Backend: `CORS_ALLOW_ORIGINS` in `app/core/config.py` (JSON array, dev defaults)
- [x] Backend: `allow_credentials=True`, explicit methods, explicit headers (incl. `Authorization` + correlation headers)
- [x] Backend: `CORS_ALLOW_ORIGINS` in env-var table in `CLAUDE.md` + `.env` example
- [x] Tests: `tests/integration/test_cors.py` — allowed origin reflected, disallowed not leaked, preflight succeeds

## Notes
- No wildcard + credentials combos anywhere; Starlette raises and the ADR documents why.
- Related: ADR-025 (API error contract the frontend consumes), ADR-019 (frontend error handling), ADR-017 (JWT auth).
- Review date: 2026-09-20

## References
- Issue #107
- FastAPI/Starlette `CORSMiddleware` docs
- Frontend issues #1 (`useFeedback`), #2 (`FeedbackModal`)