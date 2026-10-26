# ADR 026: Routing Guards — Wrapper Components with `<Outlet />`

## Status
Accepted

## Context
Frontend needs route protection for authenticated pages:
- `/` (Dashboard) — authenticated managers only
- `/notes/:id` (NoteDetail) — authenticated managers only
- `/pipeline/:runId` (Pipeline) — authenticated managers only
- `/settings` (Future) — authenticated managers only
- `/login` — public, redirects authenticated users to `/`

Options considered:
- **A. Wrapper Components with `<Outlet />`** (React Router v6 idiomatic, declarative)
- **B. Hook-Based (`useEffect` navigation)** — flash of content, not SSR-safe
- **C. Higher-Order Components** — props complexity, less idiomatic

## Decision
**Option A: Wrapper Components (`RequireAuth`, `RequireGuest`) using React Router v6 `<Outlet />`.**

## Consequences

### Positive
- Declarative: routes describe their own protection in `routes.tsx`
- No flash: `<Outlet />` renders nothing until auth resolves
- SSR-safe: no `useEffect` navigation
- Centralized loading: single spinner while `isLoading`
- ReturnTo preserved: `location.pathname + location.search` captured automatically
- Extensible: `RequireRole`, `RequirePermission` follow same pattern
- TypeScript: full type safety with `Outlet` context

### Negative
- Requires nested route structure (React Router v6)
- `Outlet` concept learning curve

### Neutral
- Auth state from Zustand store (ADR 018)
- Login page handles `returnTo` query param

## Options Considered

### Option A: Wrapper Components with `<Outlet />` (Chosen)
**Pros**: Declarative, no flash, SSR-safe, centralized loading, extensible
**Cons**: Requires nested routes, `Outlet` learning curve

### Option B: Hook-Based (`useEffect` navigation)
**Pros**: Simple, per-component control
**Cons**: Flash of content, not SSR-safe, duplicate logic

### Option C: Higher-Order Components
**Pros**: Reusable, no route restructuring
**Cons**: Props complexity, less idiomatic, TS inference tricky

## Compliance
- [ ] `RequireAuth` wrapper: checks `isAuthenticated`, `isLoading`, redirects with `returnTo`
- [ ] `RequireGuest` wrapper: redirects authenticated users to `/`
- [ ] `RequireRole` (future): role-based access for admin routes
- [ ] Routes: nested under `RequireAuth` with `Layout` wrapper
- [ ] `LoginPage`: reads `returnTo` from search params, redirects after login
- [ ] `AuthStore` (Zustand): `isAuthenticated`, `isLoading`, `login`, `logout`, `checkAuth`
- [ ] `App.tsx`: calls `checkAuth()` on mount
- [ ] Tests: `RequireAuth` loading, redirect, authenticated render

## Notes
- Auth state from Zustand `authStore` (ADR 018) with persist middleware
- `checkAuth()` called on app mount to validate stored token
- `returnTo` preserved via `location.pathname + location.search`
- `RequireRole` ready for future admin routes
- Related: ADR 017 (Auth JWT), ADR 018 (Client State), ADR 019 (401 handling), ADR 024 (Testing)
- Review date: 2026-09-20

## References
- React Router v6 Outlet: https://reactrouter.com/en/main/components/outlet
- React Router v6 Authentication: https://reactrouter.com/en/main/start/tutorial#authentication
- Zustand Persist: https://github.com/pmndrs/zustand#middleware