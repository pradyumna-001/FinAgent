# ADR 015: API Type Generation — Start Hand-Mirror, Migrate to OpenAPI Generation

## Status
Accepted

## Context
Frontend needs TypeScript types matching backend Pydantic schemas. Two approaches considered:
1. **Hand-mirror**: Manually write `src/api/types.ts`
2. **Generate**: Use `openapi-typescript` from backend's `/openapi.json`

## Decision
**Start with hand-mirror**, migrate to OpenAPI generation (`openapi-typescript`) when maintenance burden becomes painful (estimated: after 3-4 backend schema changes).

## Consequences

### Positive
- Zero initial setup cost, no tooling dependency
- High initial accuracy (you control it)
- No build-time dependency on backend running

### Negative
- Drift risk (manual sync required)
- Migration effort later when trigger hits

### Neutral
- Frontend-only types (UI state, SSE events) always hand-written
- Migration trigger: 3+ schema changes/sprint, runtime bug from drift, new dev struggles, 5+ new endpoints

## Options Considered

### Option A: Generate from OpenAPI (Immediate)
Run `openapi-typescript http://localhost:8000/openapi.json -o src/api/types.ts` on every build.

**Pros**: Zero drift, auto-propagated, exact match
**Cons**: Build-time backend dependency, setup overhead for solo dev

### Option B: Hand-Mirror Forever
Manually maintain `src/api/types.ts` indefinitely.

**Pros**: Full control, no tooling
**Cons**: Drift inevitable at scale, onboarding harder

### Option C: Hand-Mirror Now, Generate Later (Chosen)
Start manual, migrate when pain threshold crossed (3-4 schema changes/sprint, runtime bug, new dev struggles, 5+ new endpoints).

**Pros**: Low initial cost, explicit migration trigger, best of both worlds
**Cons**: Manual sync until migration, migration effort later

## Compliance
- [ ] Hand-written `src/api/types.ts` with all backend types
- [ ] Frontend-only types separated: UI state, component props, SSE events
- [ ] Migration trigger documented and monitored
- [ ] When triggered: install `openapi-typescript`, add `generate:types` script, run, commit

## Notes
- Exceptions (always hand-written): UI state, component props, form types, SSE events, `ConfidenceColor`, `StatusBadgeVariant`
- Related: ADR 012 (Detail Response), ADR 013 (SSE), ADR 021 (Forms)
- Review date: 2026-09-20 (monitor migration trigger)

## References
- Phase 1+2 Plan: FE-1.4
- FastAPI OpenAPI: `http://localhost:8000/openapi.json`
- openapi-typescript: https://github.com/drwpow/openapi-typescript