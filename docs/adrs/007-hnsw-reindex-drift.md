# ADR 007: HNSW Reindex with Drift Detection

## Status
Accepted (2026-08-19)

## Context
HNSW indexes on `morning_notes.embedding` degrade over time as inserts accumulate. `REINDEX INDEX CONCURRENTLY` rebuilds without blocking reads/writes. Need automated drift detection.

## Decision
Implement operator script `scripts/reindex_hnsw.py` with:
1. **Drift detection** — Queries `pg_stat_user_indexes` for:
   - `idx_scan` (index scans since last reindex)
   - `n_live_tup` (row count)
   - Ratio `idx_scan / n_live_tup`
   - Triggers when thresholds exceeded
2. **State tracking** — Table `hnsw_reindex_state` records `last_reindex_at`, `duration_ms`, `rows`, `status`, `error`
3. **Zero-downtime** — `REINDEX INDEX CONCURRENTLY` (PG12+)
4. **CLI** — `--dry-run`, `--force`, `--list`, configurable thresholds
5. **Cooldown** — 6-hour minimum between reindexes (matches 6h BRT = 9h UTC cron)

Default thresholds (conservative):
- `idx_scan >= 1000`
- `n_live_tup >= 10000`
- `idx_scan / n_live_tup >= 0.1`

## Rationale
- **Automated** — No manual monitoring; cron runs script every 6 hours
- **Observable** — State table provides audit trail; metrics exported to CloudWatch
- **Safe** — Concurrent reindex doesn't block production; dry-run for validation
- **Tunable** — Thresholds adjustable per index without code changes

## Consequences
- **Positive**: Proactive index maintenance; no manual intervention
- **Negative**: Thresholds need production tuning; cron dependency
- **No auto-cron** — Script designed for external invocation (systemd timer, Celery Beat, cron)

## Implementation Notes
- Migration `1787160772_add_hnsw_reindex_state_table.py` creates state table
- `tests/integration/test_reindex_hnsw.py` — 19 unit tests covering drift logic, CLI, state table
- Production: Deploy as Celery Beat periodic task or systemd timer at 9h UTC