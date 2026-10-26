# ADR 016: Frontend Additional Architectural Decisions (Index)

## Status
Accepted (Index — individual decisions in separate ADRs)

## Context
Senior engineer review identified decisions impacting frontend architecture. This ADR indexes the individual ADRs created for each decision.

## Decision
Split each high-impact decision into its own ADR for traceability. This ADR serves as an index.

## Consequences

### Positive
- Each decision traceable via its own ADR number
- Clear ownership and review per decision
- Easier to supersede individual decisions

### Negative
- More files to manage
- Need to keep index updated

### Neutral
- Low-impact decisions tracked here, not separate ADRs

## Options Considered

### Option A: Single Mega-ADR (Previous)
All decisions in one document.

**Pros**: Single file, easy to see all at once
**Cons**: Hard to review, hard to supersede, unwieldy

### Option B: Individual ADRs + Index (Chosen)
Each high-impact decision gets its own ADR; this ADR indexes them.

**Pros**: Traceable, reviewable, supersedable, follows ADR best practices
**Cons**: More files, index maintenance

## Index of Decisions

| # | Decision | ADR | Status |
|---|----------|-----|--------|
| 1 | Auth & Session Management | [ADR 017](../adrs/017-auth-jwt-with-future-hybrid.md) | Accepted |
| 2 | Client State Management | [ADR 018](../adrs/018-client-state-management.md) | Accepted |
| 3 | Error Handling Strategy | [ADR 019](../adrs/019-error-handling-strategy.md) | Accepted |
| 4 | Component Library | [ADR 020](../adrs/020-component-library.md) | Accepted |
| 5 | Form Handling + Validation | [ADR 021](../adrs/021-form-handling-validation.md) | Accepted |
| 6 | Date/Time & Timezone | [ADR 022](../adrs/022-date-time-timezone.md) | Accepted |
| 7 | Design System / Theme | [ADR 023](../adrs/023-design-system-theme.md) | Accepted |
| 8 | Testing Strategy | [ADR 024](../adrs/024-testing-strategy.md) | Accepted |
| 9 | API Error Contract | [ADR 025](../adrs/025-api-error-contract.md) | Accepted |
| 10 | Routing Guards | [ADR 026](../adrs/026-routing-guards.md) | Accepted |

### Deferred (Tracked Here)
| # | Decision | When |
|---|----------|------|
| 11 | i18n (PT-BR now, EN later) | Phase 3+ |
| 12 | Bundle optimization | Pre-production |
| 13 | Error monitoring (Sentry) | Production |
| 14 | PWA / Offline support | If mobile needed |

## Compliance
- [ ] Each high-impact decision has its own ADR with full MADR format
- [ ] This index kept updated as decisions added/superseded
- [ ] Cross-references between related ADRs maintained

## Notes
- This ADR supersedes the previous mega-ADR format
- Individual ADRs follow MADR elaborate format
- Related: All ADRs 017-026

## References
- Phase 1+2 Plan: FE-1 through FE-6
- MADR format: https://adr.github.io/madr/