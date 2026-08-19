# ADR 001: Apache AGE for MAGMA Graphs

## Status
Accepted (2026-07-31)

## Context
The MAGMA architecture requires four orthogonal graph stores:
- **Semantic** — concept/entity relationships
- **Temporal** — time-ordered event sequences
- **Causal** — cause-effect chains
- **Entity** — entity resolution and identity

Options considered:
1. **Neo4j** — dedicated graph DB, mature, but adds infrastructure complexity
2. **Apache AGE (PostgreSQL extension)** — native PostgreSQL extension, same transaction, single connection pool
3. **Separate PostgreSQL instances per graph** — overkill for MVP
4. **In-memory with persistence** — doesn't scale

## Decision
Use **Apache AGE** as the graph store for all four MAGMA graphs, running on PostgreSQL 18.

## Rationale
- **Single database** — AGE runs inside PostgreSQL; no separate service, no network latency between relational and graph data
- **ACID across relational + graph** — Single transaction can write morning_note + update AGE graphs atomically (see ADR 002)
- **Less infra** — One RDS instance, one connection pool, one backup strategy
- **SQL integration** — Can join graph queries with relational tables directly via `cypher` function
- **Team knowledge** — PostgreSQL expertise already exists; AGE uses openCypher (familiar syntax)

## Consequences
- **Positive**: Simpler deployment, atomic cross-model transactions, lower operational overhead
- **Negative**: AGE on PostgreSQL 18 has smaller community than Neo4j; some advanced graph algorithms not available; pgvector + AGE cannot run on same PostgreSQL major version (requires dual-container setup in Docker)
- **Risk**: AGE C-API compatibility with pgvector — mitigated by running pgvector on PG16 and AGE on PG18 in separate containers

## Implementation Notes
- Docker Compose: `postgres_vector` (pgvector/pgvector:pg16) + `postgres_graph` (apache/age:latest on PG18)
- Migrations create four AGE graphs: `magma_semantic`, `magma_temporal`, `magma_causal`, `magma_entity`
- Application code uses `app/memory/{semantic,temporal,causal,entity,magma}.py` modules