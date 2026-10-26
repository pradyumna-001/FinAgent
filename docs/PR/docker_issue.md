# PR: Isolate Relational/Vector and Graph Storage Tiers to Resolve Dependency Mismatches

## Summary
This PR refactors the database architecture from a single-container multi-extension layout to an isolated multi-service topology. This resolves critical compilation and runtime dependency blocks between `pgvector` and `Apache AGE`.

---

## Technical Post-Mortem & Root Cause Analysis

### 1. Build Cache Invalidation Issue
* **Symptom:** Modifications to the underlying setup scripts were not reflected during standard `docker compose up` execution.
* **Root Cause:** Docker’s layer caching mechanisms skipped evaluation of modified runtime execution scripts because the instruction signatures in the orchestrator configuration file remained identical.
* **Resolution:** Enforced clean state execution using the `--build` and `-v` flags (`docker compose up -d --build`).

### 2. Header Compilation Failure (`postgres.h`)
* **Symptom:** Source compilation of `pgvector` halted with exit code 2: `src/bitutils.c:1:10: fatal error: postgres.h: No such file or directory`.
* **Root Cause:** Interface mismatch between the base image runtime and the build-essential tooling. The `apache/age:latest` upstream image references a PostgreSQL 18 engine core. The build scripts executed `apt-get install postgresql-server-dev-16`. The internal build utility (`pg_config`) queried paths matching the runtime version (v18), which lacked the corresponding development headers.

### 3. C-API Signature Incompatibility (`vacuum_delay_point`)
* **Symptom:** Upgrading development tooling to `postgresql-server-dev-18` resolved header resolution but failed during binary compilation: `src/hnswvacuum.c:52:17: error: too few arguments to function ‘vacuum_delay_point’`.
* **Root Cause:** Breaking change in the PostgreSQL 18 kernel core API. In PostgreSQL 18, the internal function signature for cost-based vacuum throttling was modified to require an explicit boolean parameters block: `extern void vacuum_delay_point(bool is_analyze);`. The frozen release branch of `pgvector (v0.7.4)` invokes this function with zero arguments, violating the updated engine contract.

---

## Architectural Resolution: Microservice Separation

To avoid maintaining unreleased upstream source patches or compromising subsystem stability, the data tier has been decoupled into single-responsibility services via `docker-compose.yml`.

### System Configuration Breakdown

1. **`postgres_vector` Service:**
   * **Engine Foundation:** `pgvector/pgvector:pg16` (PostgreSQL 16 base).
   * **Port Allocation:** `5432:5432`
   * **Responsibility:** Handles relational schemas, application transactional data, and high-dimensional vector embeddings via `pgvector v0.8.5`.
   * **Initialization:** Executes `scripts/init_vector.sql` to instantiate the extension within a compatible runtime engine context.

2. **`postgres_graph` Service:**
   * **Engine Foundation:** `apache/age:latest` (PostgreSQL 18 base).
   * **Port Allocation:** `5433:5432`
   * **Responsibility:** Handles agent semantic memory networks and contextual knowledge graphs via `Apache AGE v1.7.0`.
   * **Initialization:** Executes `scripts/init_graph.sql` to instantiate the graph framework within its native environment.

---

## Verification Logs

Both extensions successfully register inside their independent execution contexts:

### Vector Extension Telemetry
```sql
-- Query executed against port 5432
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
-- Output:
-- vector | 0.8.5s