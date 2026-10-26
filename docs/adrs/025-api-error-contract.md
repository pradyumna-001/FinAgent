# ADR 025: API Error Contract — Standardized Error Responses

## Status
Accepted

## Context
Frontend needs consistent error handling across all backend endpoints. Current backend returns inconsistent shapes:
- 400: `{"detail": "manager_id header required"}`
- 404: `{"detail": "Morning note not found"}`
- 500: Raw exception traceback

Frontend requires machine-readable error codes, field-level validation details, user-friendly messages, standardized retry/auth/conflict handling.

## Decision
**Standardize all backend error responses to a single JSON contract** with predefined error codes.

## Consequences

### Positive
- Single error contract across all endpoints
- Machine-readable codes for routing logic
- Field-level validation details for form mapping
- Standardized retry/auth/conflict handling

### Negative
- Requires backend coordination for error contract
- All routes must be updated to use `ApiError`

### Neutral
- Error codes table serves as contract documentation
- Frontend `ApiError` class with type guards

## Options Considered

### Option A: Ad-Hoc per Route (Current)
Each route returns different error shape.

**Pros**: No coordination needed
**Cons**: Frontend can't reliably handle, inconsistent UX

### Option B: HTTP Status Only
Use status codes only, no error codes.

**Pros**: Simple
**Cons**: Can't distinguish 400 types, no field details

### Option C: Standardized Contract (Chosen)
All errors: `{ code, message, details?, timestamp, path }` with predefined codes.

**Pros**: Complete frontend handling, type-safe, testable, documented
**Cons**: Backend coordination required

## Compliance
- [ ] Backend: `ApiError` class + `ErrorCodes` enum in `app/api/errors.py`
- [ ] Backend: Global exception handlers in `app/main.py`
- [ ] Backend: All routes raise `ApiError` with proper codes
- [ ] Frontend: `ApiError` class with type guards (`isRetryable`, `isValidationError`, etc.)
- [ ] Frontend: Axios interceptor routes by error type
- [ ] Frontend: TanStack Query retries 5xx/network 3x with exponential backoff
- [ ] Frontend: `useApiError` hook maps `details` to RHF fields
- [ ] Contract tests for `ApiError.fromResponse`

## Error Codes Reference

| Status | Code | Frontend Action |
|--------|------|-----------------|
| 400 | `MISSING_HEADER` | Toast + redirect login |
| 401 | `UNAUTHORIZED` | Interceptor → logout + redirect |
| 403 | `RLS_VIOLATION` | Toast "Access denied" |
| 404 | `NOT_FOUND` | Toast + redirect dashboard |
| 409 | `IDEMPOTENCY_KEY_EXISTS` | Toast with existing run ID |
| 422 | `VALIDATION_ERROR` | `setErrors(details)` → field errors |
| 5xx | `INTERNAL_ERROR`, etc. | Toast + auto-retry (3x) |
| 0 | `NETWORK_ERROR` | Toast + auto-retry |

## Notes
- Response shape: `{ code, message, details?, timestamp, path }`
- Frontend `ApiError` class with type guards (`isRetryable`, `isValidationError`, etc.)
- Axios interceptor routes: auth→logout, validation→form, retryable→retry, other→toast
- Forms: `useApiError` hook maps `details` to RHF fields
- Related: ADR 019 (Error Handling), ADR 021 (Forms), ADR 024 (Testing)
- Review date: 2026-09-20

## References
- ADR 019: Error Handling Strategy (frontend interceptor, toast, boundary)
- ADR 021: Form Handling (useApiError hook, setErrorsFromApiError)
- FastAPI Exception Handlers: https://fastapi.tiangolo.com/tutorial/handling-errors/
- Pydantic Error Details: https://docs.pydantic.dev/latest/concepts/validation_errors/