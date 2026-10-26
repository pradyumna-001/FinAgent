# ADR 017: Authentication — JWT Now, Hybrid (JWT + Refresh Cookie) Later

## Status
Accepted

## Context
Frontend needs to send `manager_id` header for RLS. Backend has no auth endpoints. Options considered:
- **A. Mock/Hardcode** — Dev only, no security
- **B. Manager Selector** — Header-based, no real auth
- **C. JWT (Stateless)** — Short-lived access token, re-login on expiry
- **D. Session Cookie (Stateful)** — Server-side sessions in Redis
- **E. OAuth/OIDC** — External identity provider

## Decision
**Implement Option C (JWT) now** with a plan to **evolve to Hybrid (JWT + Refresh Token in httpOnly Cookie)** before production.

## Consequences

### Positive
- No Redis session store needed (stateless)
- Works with Celery workers (pass manager_id in task payload)
- OAuth (Option E) returns JWTs — natural evolution
- ~2 days to implement vs ~3 days for sessions
- Short expiry (30 min) limits exposure

### Negative
- No revocation until expiry (acceptable for 3 users)
- Token in memory (not localStorage) — XSS safe but manual refresh needed
- Migration to hybrid required before production

### Neutral
- Migration path documented: JWT → Hybrid → OAuth
- Phase 2: JWT only (30 min, re-login)
- Phase 3/4: Hybrid (15 min JWT + refresh cookie)
- Phase 5+: OAuth/OIDC

## Options Considered

### Option A: Mock/Hardcode
Hardcode `manager_id: 1` in dev.

**Pros**: Zero backend work, unblocks Day 1
**Cons**: No real security, cannot switch managers, technical debt

### Option B: Manager Selector
Dropdown in header → select manager → stores in localStorage → header interceptor.

**Pros**: Works with current RLS, supports multi-manager, no backend auth
**Cons**: No authentication, no audit trail, not production-ready

### Option C: JWT (Stateless) (Chosen)
Short-lived access token (30 min), re-login on expiry.

**Pros**: Stateless, works with Celery, OAuth-ready, ~2 days, short expiry limits exposure
**Cons**: No revocation until expiry, migration to hybrid needed

### Option D: Session Cookie (Stateful)
Server-side sessions in Redis, httpOnly cookie.

**Pros**: Immediate revocation, secure by default
**Cons**: Requires Redis, Celery needs cookie parsing, ~3 days, extra exchange for OAuth

### Option E: OAuth/OIDC
External identity provider (Google, Microsoft, Auth0).

**Pros**: No password management, enterprise SSO, MFA built-in
**Cons**: External dependency, complex setup, overkill for 3 managers

## Compliance
- [ ] Backend: `app/core/security.py` with `create_access_token`/`decode_access_token`
- [ ] Backend: `app/api/routes/auth.py` with `POST /auth/login`
- [ ] Backend: `app/api/deps.py` with `get_current_manager` dependency
- [ ] Backend: RLS uses `manager_id` from JWT payload
- [ ] Frontend: `AuthProvider` with memory-only token storage
- [ ] Frontend: Axios interceptor adds `Authorization: Bearer <token>`
- [ ] Frontend: 401 handler clears state, redirects to `/login`
- [ ] Migration plan documented for Hybrid (Phase 3/4)

## Notes
- Phase 2 (Frontend): JWT only, 30 min expiry, re-login
- Phase 3/4 (Backend): Hybrid — 15 min JWT + refresh token in httpOnly cookie
- Phase 5+: OAuth/OIDC for enterprise SSO
- Related: ADR 016 (Auth section), ADR 019 (Error Handling 401), ADR 026 (Routing Guards)
- Review date: 2026-09-20 (before production deploy)

## References
- ADR 016: Frontend Additional Decisions (Auth section)
- Phase 1+2 Plan: Backend #03b, #03c, #05d; Frontend FE-1 through FE-6
- OAuth 2.0 + OIDC: Future Option E
- JWT Best Practices: RFC 8725, OWASP JWT Cheat Sheet