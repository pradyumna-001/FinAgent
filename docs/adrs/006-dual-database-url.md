# ADR 006: Dual DATABASE_URL Pattern (App Role Split)

## Status
Accepted (2026-08-19)

## Context
PostgreSQL security model: superuser (migrations) vs least-privilege app role (runtime). Previously used single `DATABASE_URL` with superuser for everything.

## Decision
Split into two environment variables:
- **`MIGRATION_DATABASE_URL`** — Superuser (or elevated role); used ONLY by Alembic for DDL
- **`DATABASE_URL`** — `finagent_app` role; used by application at runtime

`finagent_app` role:
```sql
CREATE ROLE finagent_app WITH NOSUPERUSER NOBYPASSRLS LOGIN;
GRANT USAGE ON SCHEMA public TO finagent_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON managers, companies, portfolios, portfolio_holdings, morning_notes, recommendations TO finagent_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finagent_app;
```

## Rationale
- **Least privilege** — Runtime code cannot DROP/CREATE/ALTER tables; cannot bypass RLS
- **Defense in depth** — Even if app is compromised, attacker cannot destroy schema
- **Auditability** — Clear separation of migration-time vs runtime credentials
- **Compliance** — Meets security review requirements for financial applications

## Consequences
- **Positive**: Strong security posture; RLS enforced at database level for app role
- **Negative**: Two sets of credentials to manage; CI/CD must inject both
- **Migration complexity**: Alembic `env.py` reads `MIGRATION_DATABASE_URL`; app uses `DATABASE_URL`

## Implementation Notes
- Migration `7757cc467c23_create_finagent_app_role_and_grants.py` creates role and grants
- Migration `590bbac20489_merge_heads_for_app_role_split.py` merges parallel migration heads
- `alembic/env.py` reads `MIGRATION_DATABASE_URL` (falls back to `DATABASE_URL` if not set)
- `tests/conftest.py` uses `MIGRATION_DATABASE_URL` for `alembic upgrade heads`
- `tests/integration/test_app_role.py` — 6 behavioral probes verifying `finagent_app` permissions