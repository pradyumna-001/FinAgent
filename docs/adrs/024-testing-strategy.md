# ADR 024: Testing Strategy — Vitest + React Testing Library + Playwright

## Status
Accepted

## Context
Frontend needs a testing pyramid covering unit, component, integration, and E2E tests. Constraints: CI <3 minutes, TypeScript-first, accessibility built-in, learning-focused.

## Decision
**Option A: Vitest + React Testing Library + Playwright** (Vite-native, fast, modern).

## Consequences

### Positive
- Vite-native (same aliases, plugins, env)
- Fast (~10x faster than Jest)
- RTL teaches accessible, user-centric testing
- Playwright best E2E for modern apps
- TypeScript-first, unified tooling

### Negative
- Two test runners (Vitest + Playwright)
- Playwright separate install

### Neutral
- E2E limited to 2-3 critical paths
- Visual regression deferred

## Options Considered

### Option A: Vitest + RTL + Playwright (Chosen)
**Pros**: Vite-native, fast, RTL best practices, Playwright modern E2E
**Cons**: Two runners

### Option B: Jest + RTL + Playwright
**Pros**: Mature ecosystem
**Cons**: Slower, config divergence from Vite, ts-jest overhead

### Option C: Vitest Only
**Pros**: Simple, one runner
**Cons**: No real browser testing, misses integration bugs

### Option D: Cypress
**Pros**: Great DX, time-travel debugging
**Cons**: Heavier, slower, less TS-native

## Compliance
- [ ] `vitest.config.ts` with jsdom, coverage thresholds (80/80/70/80)
- [ ] `src/test/setup.ts` with mocks (matchMedia, localStorage, crypto, ResizeObserver)
- [ ] Unit tests: pure functions, hooks, Zod schemas
- [ ] Component tests: UI primitives + forms (RTL + user-event)
- [ ] Integration tests: pages + hooks + mocked API
- [ ] E2E: 2-3 critical paths (login→trigger→view→feedback)
- [ ] CI: `test` job (Vitest) + `e2e` job (Playwright) < 3 min total
- [ ] Coverage thresholds: 80% lines/functions/statements, 70% branches

## Notes
- Testing principles: behavior over implementation, accessibility queries, user-event, mock at boundary, test error states
- File structure: `src/**/*.test.ts`, `src/components/**/*.test.tsx`, `src/pages/**/*.test.tsx`, `e2e/critical-paths.spec.ts`
- Related: ADR 019 (Error Handling tests), ADR 021 (Form tests), ADR 023 (Design System tests)
- Review date: 2026-09-20

## References
- Vitest: https://vitest.dev/
- RTL: https://testing-library.com/docs/react-testing-library/intro/
- Playwright: https://playwright.dev/
- Testing Trophy: https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications
- Accessibility Testing: https://testing-library.com/docs/queries/about/#priority