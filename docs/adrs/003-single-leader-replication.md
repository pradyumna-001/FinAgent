# ADR 003: Single-Leader Replication with Read Scaling

## Status
Accepted (2026-07-31)

## Context
Production workload pattern:
- **Write burst**: 6:00 AM BRT daily — Celery Beat triggers pipeline for all managers/companies (~15 parallel runs)
- **Read pattern**: Throughout the day — managers read morning notes via API dashboard
- **Peak reads**: 6:30–9:00 AM (managers reviewing notes)

Options:
1. **Multi-leader** — Complex conflict resolution; overkill for single-writer pattern
2. **Single-leader + read replicas** — Standard PostgreSQL pattern; matches workload
3. **No replicas** — Single instance; risk of read contention during morning peak

## Decision
Use **single-leader PostgreSQL (RDS Multi-AZ) with read replicas** for production.
- Writer: RDS primary instance (handles 6 AM write burst)
- Readers: 2–3 read replicas (absorb dashboard read traffic 6:30 AM onward)
- Connection routing: Application uses separate `DATABASE_URL_READ` for SELECT queries

## Rationale
- **Write pattern is predictable** — Single daily burst; primary handles easily
- **Read pattern is sustained** — Replicas offload read traffic from primary
- **RDS manages replication** — Native PostgreSQL streaming replication; automatic failover
- **Cost-effective** — db.r6g.xlarge primary + 2× db.r6g.large replicas < single db.r6g.2xlarge

## Consequences
- **Positive**: Automatic failover, read scaling, managed by AWS
- **Negative**: Replication lag (typically < 100ms); reads may see slightly stale data (acceptable for morning notes)
- **Application change**: Need read/write split in connection pooling (SQLAlchemy `engine` vs `engine_read`)

## Implementation Notes
- `app/core/config.py` exposes `DATABASE_URL` (writer) and `DATABASE_URL_READ` (reader)
- `app/db/session.py` creates two engines; `get_session` uses writer, `get_read_session` uses reader
- Celery workers use writer; API endpoints use reader for GET, writer for POST