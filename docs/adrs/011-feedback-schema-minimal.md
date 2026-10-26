# ADR 011: Feedback Schema — Minimal Viable

## Status
Accepted

## Context
Frontend needs a `POST /morning-notes/{id}/feedback` endpoint (FE-5.2) for managers to override recommendations. Backend has no `Feedback` model yet (FE-5.1). The schema must support the FeedbackModal (action, justification, comment), RLS isolation (manager_id from header, morning_note_id from URL), and audit trail (created_at).

## Decision
Create minimal `Feedback` table with only fields required for the MVP. Defer learning/analytics fields to Phase 3.

## Consequences

### Positive
- Simple, minimal migration, unblocks frontend Days 5-6
- Nullable extensions can be added later without migration (ALTER TABLE ADD COLUMN)
- Clear separation: MVP fields vs Phase 3 analytics fields

### Negative
- Phase 3 MAGMA/evals will need a follow-up migration for learning fields
- Accuracy calculation requires JOIN to `recommendations` table (acceptable)

### Neutral
- RLS policy follows existing pattern: `USING (manager_id = current_setting('app.manager_id')::int)`

## Options Considered

### Option A: Minimal Schema (Chosen)
| Field | Included? | Reason |
|-------|-----------|--------|
| `morning_note_id` | ✅ | FK to note being judged |
| `manager_id` | ✅ | RLS requires it; from `X-Manager-Id` header |
| `action` | ✅ | Manager's override: buy/sell/keep |
| `justification` | ✅ | Required text explaining override |
| `comment` | ✅ | Optional free-text context |
| `created_at` | ✅ | Audit + time-series analytics |
| `confidence_delta` | ❌ | Defer to Phase 3 (MAGMA #18) |
| `tags` | ❌ | Defer to Phase 3 (evals #25) |
| `original_*` snapshots | ❌ | Defer; can be joined from `recommendations` table |

**Pros**: Unblocks frontend immediately, minimal migration risk, explicit deferral
**Cons**: Follow-up migration needed for Phase 3, JOIN required for accuracy calc

### Option B: Extended Schema (All Fields)
Include `confidence_delta`, `tags`, `original_action`, `original_confidence` from day one.

**Pros**: No follow-up migration, complete data for analytics
**Cons**: Over-engineering for MVP, unused columns in production, migration complexity

### Option C: JSONB Flexible Schema
Single `metadata JSONB` column for all extensible fields.

**Pros**: Maximum flexibility, no migrations for new fields
**Cons**: No schema enforcement, query complexity, no type safety

## Compliance
- [ ] Migration created: `alembic/versions/xxx_feedback_minimal.py`
- [ ] SQLAlchemy model added: `app/db/models.py` with `Feedback` class
- [ ] RLS policy: `USING (manager_id = current_setting('app.manager_id')::int)`
- [ ] API route: `app/api/routes/feedback.py` with `POST /morning-notes/{id}/feedback`
- [ ] Frontend hook: `useFeedback` + `FeedbackButton` + `FeedbackModal`
- [ ] Integration test: feedback submission with RLS verification

## Notes
- Related: ADR 017 (Auth JWT), ADR 019 (Error Handling), ADR 021 (Forms)
- Phase 3 trigger: When MAGMA feedback loop (#18) or evals baseline (#25) starts
- Review date: 2026-09-20 (after Phase 2 completion)

## References
- Phase 1+2 Plan: FE-5.1 through FE-5.5
- MAGMA feedback loop: Issue #18 (`update_magma_from_feedback()`)
- Evals baseline: Issue #25 (accuracy calc needs feedback snapshots)