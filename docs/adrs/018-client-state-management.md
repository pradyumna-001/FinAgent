# ADR 018: Client State Management — Context + Zustand Hybrid

## Status
Accepted

## Context
Frontend uses TanStack Query for server state (API data, caching, mutations). Need a strategy for client-only UI state:
- Ephemeral UI (modals, sidebars, dropdowns, toasts)
- Cross-component state (selected note, active tab)
- User preferences (theme, density, filters)
- Form drafts (handled by React Hook Form)
- Auth state (covered by ADR 017)

## Decision
**Hybrid approach: React Context for Auth + Theme, Zustand for everything else.**

## Consequences

### Positive
- Context for SSR-relevant, low-frequency state (Auth, Theme)
- Zustand for high-frequency, cross-component UI state with selective subscription
- No prop drilling, no Context performance trap
- Zustand persist middleware handles user preferences automatically
- Small bundle (~1.5kb), no Provider wrapper needed

### Negative
- Two state solutions to understand
- Zustand requires `persist` middleware for localStorage sync

### Neutral
- Form drafts stay in React Hook Form (local)
- Cross-page selection via URL (React Router)

## Options Considered

### Option A: Pure Context
Single `UIContext` for all client state.

**Pros**: Single mental model, built-in
**Cons**: Re-renders all consumers on any change (performance trap with 6+ pages)

### Option B: Redux Toolkit
Full Redux with slices, thunks, RTK Query.

**Pros**: Opinionated, battle-tested, DevTools
**Cons**: ~12kb vs 1.5kb, RTK Query redundant with TanStack Query, boilerplate

### Option C: Jotai
Atomic state management.

**Pros**: Granular atoms, derived state
**Cons**: Cognitive overhead, no persist middleware, overkill for simple UI state

### Option D: Context + Zustand Hybrid (Chosen)
Context for Auth + Theme (SSR, low frequency); Zustand for toasts, modals, sidebar, preferences (high frequency, selective subscription).

**Pros**: Right tool per state type, performance, small bundle, SSR-compatible
**Cons**: Two patterns to learn

## Compliance
- [ ] `AuthProvider` + `ThemeProvider` (React Context)
- [ ] `uiStore` (Zustand) with toasts, modals, sidebar, preferences
- [ ] `persist` middleware for density, date range
- [ ] Selective subscription: `useUIStore((s) => s.addToast)`
- [ ] Provider tree: `AuthProvider` → `ThemeProvider` → `UIStore` optional

## Notes
- Implementation order: Day 1 Context, Day 2 Zustand toasts, Day 3 modals/sidebar, Day 4 persist
- Related: ADR 017 (Auth), ADR 019 (Error Handling toasts), ADR 021 (Forms), ADR 023 (Theme)
- Review date: 2026-09-20

## References
- ADR 016: Frontend Additional Decisions (Client State section)
- ADR 017: Auth JWT (AuthProvider uses Context)
- TanStack Query: Server state (already chosen)
- React Hook Form: Form state (local)
- Zustand: https://github.com/pmndrs/zustand
- Zustand persist middleware: https://github.com/pmndrs/zustand#middleware