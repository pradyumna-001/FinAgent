# ADR 014: Frontend CI — Every PR

## Status
Accepted

## Context
Phase 1+2 Plan line 168: "Frontend CI — run on every PR? Or only on feature/frontend-v0 merges?"

## Decision
Run frontend CI (build + lint + typecheck) on **every pull request** to `main`, same as backend.

## Consequences

### Positive
- Consistency with backend CI (runs on every PR)
- Type errors, lint failures, build breaks caught before merge
- `feature/frontend-v0` merges clean because every commit validated
- Cost ~30-60s per PR (npm ci cached) — negligible

### Negative
- Slight CI time increase per PR
- Requires Node.js setup in GitHub Actions

### Neutral
- E2E tests (Playwright) deferred until critical paths exist
- Visual regression deferred until UI stabilizes
- Bundle size budget deferred until optimization phase

## Options Considered

### Option A: Every PR (Chosen)
Run `npm run lint`, `npm run typecheck`, `npm run build` on every PR to `main`.

**Pros**: Early detection, consistent with backend, prevents broken merges
**Cons**: Minor CI time cost

### Option B: Only on `feature/frontend-v0` merges
Run CI only when the frontend feature branch merges.

**Pros**: Fewer CI runs
**Cons**: Broken code can sit in branch, inconsistent with backend, merge surprises

### Option C: Manual Only
Run CI manually via workflow_dispatch.

**Pros**: Zero automated cost
**Cons**: No safety net, human error, defeats CI purpose

## Compliance
- [ ] Workflow: `.github/workflows/ci.yml` with `frontend` job
- [ ] Branch protection: `ci/frontend` required status check on `main`
- [ ] Scripts: `package.json` has `lint`, `typecheck`, `build`
- [ ] Cache: `npm` cache configured in workflow

## Notes
- E2E tests (Playwright) added when critical paths exist
- Visual regression added when UI stabilizes
- Bundle size budget added when optimizing
- Related: ADR 024 (Testing Strategy), ADR 023 (Design System)
- Review date: 2026-09-20

## References
- Phase 1+2 Plan: FE-6.5
- Backend CI: `.github/workflows/ci.yml` (existing)
- Frontend scripts: `package.json` (lint, typecheck, build)