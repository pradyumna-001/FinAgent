# ADR 008: CI Integration Tests with PostgreSQL Service Container

## Status
Accepted (2026-08-19)

## Context
Unit tests run without database (fast, isolated). Integration tests need real PostgreSQL with pgvector + AGE. Previous CI only ran unit tests.

## Decision
Add `integration-tests` job to single `.github/workflows/ci.yml`:
- **Service container**: `pgvector/pgvector:pg16` (includes pgvector + Apache AGE)
- **Health check**: `pg_isready` with 10 retries
- **Migration step**: `alembic upgrade heads` (plural — multiple migration heads exist)
- **Test execution**: `pytest tests/integration/ -v` (all 49 tests)
- **Timeout**: 10 minutes
- **Single workflow** — Keeps unit + integration together for simplicity

## Rationale
- **Real database** — Catches RLS, migration, constraint issues unit tests miss
- **pgvector/pgvector:pg16** — Matches production RDS setup; includes AGE
- **`upgrade heads`** — Migration history has parallel branches (app role split + HNSW reindex); singular `head` fails
- **Single file** — Easier to maintain; can split to `ci-integration.yml` later if runtime grows

## Consequences
- **Positive**: Full integration coverage on every push; catches schema drift early
- **Negative**: Slower CI (~3-5 min); service container startup adds latency
- **Flakiness risk**: Testcontainers in CI is flaky on shared runners; service container more reliable

## Implementation Notes
- `tests/conftest.py` updated: `alembic upgrade heads` (matches CI)
- 115 total tests: 66 unit + 49 integration
- All CI checks: `ruff`, `mypy`, unit tests, integration tests
- Branch protection requires both `unit-tests` and `integration-tests` to pass