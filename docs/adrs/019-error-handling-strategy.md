# ADR 019: Error Handling Strategy — Unified System

## Status
Accepted

## Context
Frontend needs consistent error handling across:
- Network errors (offline, timeout)
- HTTP errors (400, 401, 403, 404, 422, 500, 502, 503)
- Validation errors (field-level)
- React render errors
- Unhandled promise rejections

Current backend returns inconsistent error shapes. Need standardized contract + frontend system.

## Decision
**Unified error system combining:**
1. **Backend**: Standardized `ApiError` class with consistent JSON shape
2. **Frontend**: Axios interceptor + TanStack Query retry + React Error Boundary + Toast system (Zustand)
3. **Forms**: `useApiError` hook for validation error handling

## Consequences

### Positive
- Single error contract across all endpoints
- Centralized HTTP handling via Axios interceptor
- Automatic retry for transient errors (5xx, network)
- Field-level validation errors mapped to forms
- Render errors caught by Error Boundary
- Toast system integrated with Zustand

### Negative
- Requires backend coordination for error contract
- Multiple layers (interceptor, Query retry, Boundary, forms)

### Neutral
- Sentry integration deferred to production
- E2E error flows tested via Playwright

## Options Considered

### Option A: Ad-Hoc per Component
Each hook/component handles its own errors.

**Pros**: Simple to start
**Cons**: Inconsistent UX, duplicate code, no centralized logging, hard to change

### Option B: TanStack Query + Axios Interceptor Only
Global HTTP handling + Query retry, no Error Boundary.

**Pros**: Covers HTTP errors, simple
**Cons**: Misses React render errors, no validation error mapping

### Option C: React Error Boundary Only
Catch render errors, handle HTTP in components.

**Pros**: Catches render crashes
**Cons**: Duplicate HTTP handling, inconsistent

### Option D: Unified System (Chosen)
Backend `ApiError` contract + Axios interceptor + TanStack Query retry + Error Boundary + Toast system + Form hook.

**Pros**: Complete coverage, consistent UX, centralized, type-safe, testable
**Cons**: More initial setup, backend coordination needed

## Compliance
- [ ] Backend: `ApiError` class with codes (`VALIDATION_ERROR`, `NOT_FOUND`, `RLS_VIOLATION`, etc.)
- [ ] Backend: Global exception handlers in `app/main.py`
- [ ] Backend: All routes raise `ApiError` with proper codes
- [ ] Frontend: `ApiError` class with type guards (`isRetryable`, `isValidationError`, etc.)
- [ ] Frontend: Axios interceptor routes by error type
- [ ] Frontend: TanStack Query retry config (3x exponential backoff for retryable)
- [ ] Frontend: Toast system (Zustand) + `Toaster` component
- [ ] Frontend: `ErrorBoundary` + fallback UI
- [ ] Frontend: `useApiError` hook maps `details` to RHF fields
- [ ] Contract tests for `ApiError.fromResponse`

## Notes
- Error flow table: Network→retry, 401→logout, 403→toast, 404→toast, 422→field errors, 5xx→retry, render→Boundary
- Implementation order: Day 1 backend+interceptor, Day 2 toast+Boundary, Day 3 form hook+retry config, Day 4 Sentry
- Related: ADR 017 (401 handling), ADR 018 (Zustand toasts), ADR 021 (Forms), ADR 024 (Testing), ADR 025 (API Error Contract)
- Review date: 2026-09-20

## References
- ADR 016: Frontend Additional Decisions (Error Handling section)
- ADR 017: Auth JWT (401 handling)
- ADR 018: Client State (Toast system uses Zustand)
- ADR 024: Testing Strategy (contract tests)
- ADR 025: API Error Contract (backend contract details)
- TanStack Query retry: https://tanstack.com/query/v5/docs/reference/useQuery#retry
- Axios interceptors: https://axios-http.com/docs/interceptors
- React Error Boundaries: https://react.dev/learn/error-boundaries