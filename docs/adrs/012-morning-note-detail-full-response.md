# ADR 012: GET /morning-notes/{id} — Full Detail Response

## Status
Accepted

## Context
Frontend NoteDetailPage (FE-3.3) needs complete morning note data: note text, confidence scores per section, data freshness, DataFlags, recommendation, and relation names. Current list endpoint returns minimal fields via raw SQL.

## Decision
Implement `GET /morning-notes/{id}` returning full `MorningNote` + joined `Recommendation` + relation names in a single response.

## Consequences

### Positive
- Single API call → better UX, simpler loading state
- ~5-10 KB payload → negligible with TanStack Query caching
- NoteDetail is a "focus" view — user expects complete data
- SSE streams progress; detail is the final consolidated view

### Negative
- Larger payload than minimal response (acceptable for detail view)
- ORM query slightly more complex than raw SQL

### Neutral
- Option C (`?include=...`) deferred to Phase 3+ when needed
- RLS enforced via `SET LOCAL app.manager_id` before query

## Options Considered

### Option A: Full Detail Response (Chosen)
Return all fields in single response: `MorningNote` + `Recommendation` + joined relations (`manager_name`, `company_ticker`, `company_name`).

**Pros**: Single call, simpler frontend loading, cached by TanStack Query
**Cons**: Slightly larger payload, ORM complexity

### Option B: Minimal + Separate Calls
Basic note + separate endpoints for `/recommendations/{note_id}`, `/flags/{note_id}`, `/relations/{note_id}`.

**Pros**: Smaller initial payload
**Cons**: 3+ round trips, complex loading states, N+1 risk on lists

### Option C: Configurable Includes
`GET /morning-notes/{id}?include=recommendation,flags,freshness,relations`

**Pros**: Flexible, optimal for list expansions
**Cons**: More backend complexity, caching complexity, over-engineering for MVP

## Compliance
- [ ] Backend: SQLAlchemy ORM query with `selectinload` for relations
- [ ] Backend: RLS `SET LOCAL app.manager_id` before query
- [ ] Backend: 404 if note not found or RLS filters out
- [ ] Frontend: `MorningNoteDetail` type in `src/api/types.ts`
- [ ] Frontend: `useMorningNoteDetail` hook with TanStack Query
- [ ] Frontend: NoteDetailPage renders all sections

## Notes
- Future Option C: Add `?include=` parameter when list-item expansion needed
- Related: ADR 013 (SSE), ADR 021 (Forms), ADR 022 (Date/Time)
- Review date: 2026-09-20

## References
- Phase 1+2 Plan: FE-3.1, FE-3.2, FE-3.3
- Frontend type: `MorningNoteDetail` in `src/api/types.ts`
- Backend models: `MorningNote`, `Recommendation` in `app/db/models.py`