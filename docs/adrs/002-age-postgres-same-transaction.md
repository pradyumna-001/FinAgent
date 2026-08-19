# ADR 002: AGE + PostgreSQL in Same Transaction

## Status
Accepted (2026-07-31)

## Context
Morning notes must be persisted atomically with MAGMA graph updates. If the graph write fails, the morning note must not be saved (and vice versa).

Options:
1. **Two-phase commit** — Complex, not supported well by PostgreSQL + AGE
2. **Eventual consistency** — Background job reconciles; risk of divergence
3. **Single transaction across pgvector PG + AGE PG** — Impossible (separate containers/instances)
4. **Single transaction on AGE PostgreSQL** — Write both relational data (morning_notes, recommendations) AND graph data in one transaction on the AGE instance

## Decision
Run both the relational schema (morning_notes, recommendations, managers, companies, portfolios) AND the AGE graphs on the **same PostgreSQL instance (PG18 with AGE extension)**. Use a single transaction for `INSERT morning_notes` + `INSERT recommendations` + `AGE graph mutations`.

## Rationale
- **Atomicity** — Database guarantees all-or-nothing; no reconciliation jobs needed
- **Simplicity** — One connection, one transaction, standard `BEGIN`/`COMMIT`/`ROLLBACK`
- **Performance** — No network round-trip between separate DBs
- **RLS works uniformly** — Row Level Security applies to both relational and graph data in same session

## Consequences
- **Positive**: Strong consistency, simple code, single source of truth
- **Negative**: pgvector (for HNSW embeddings) requires PG16; must run pgvector on separate PG16 instance or use PG18 with pgvector extension (if available). Current setup uses dual-container: PG16 for vectors, PG18 for AGE + relational.
- **Migration**: Schema migrations must run on AGE instance; vector operations on PG16 instance

## Implementation Notes
- Production: RDS PostgreSQL 18 with both `age` and `vector` extensions enabled (if RDS supports both on same version), or separate RDS instances with application-level coordination
- For now: Dual-container Docker Compose; application writes morning notes to AGE instance, embeddings to PG16 instance
- `scripts/reindex_hnsw.py` operates on PG16 instance only