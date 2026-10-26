# ADR 013: SSE Event Format — In-Memory Queue (Option C)

## Status
Accepted

## Context
Frontend PipelinePage (FE-4.4) needs real-time agent progress via SSE. Current stub sends one event. Real pipeline has 5 nodes: `macro → company/quant (parallel) → risk → editor`.

## Decision
Use **Option C: In-memory asyncio.Queue per pipeline_run_id** for MVP. Upgrade to **Option B: Redis pub/sub** when scaling to multiple workers.

## Consequences

### Positive
- Simple implementation, no extra infrastructure
- Same event schema works for both Option C and B (no frontend changes on upgrade)
- Works with single FastAPI process (current architecture)

### Negative
- Limited to single worker process (upgrade path documented)
- Queue cleanup must be handled explicitly

### Neutral
- Upgrade to Redis pub/sub (Option B) when ECS tasks > 1
- No frontend changes required for upgrade

## Options Considered

### Option A: Callback Hooks in Graph
Wrap each node to emit SSE via callback passed through state.

**Pros**: Clean separation, testable
**Cons**: Need to pass callback through state, more complex graph setup

### Option B: Redis Pub/Sub
Agents publish to Redis channel; SSE endpoint subscribes.

**Pros**: Scales horizontally, decoupled
**Cons**: Requires Redis infrastructure, extra complexity for MVP

### Option C: In-Memory asyncio.Queue (Chosen)
`Dict[str, asyncio.Queue]` keyed by `pipeline_run_id`. Graph nodes emit via callback. SSE endpoint subscribes to queue.

**Pros**: Simple, no extra infrastructure, same schema as Option B
**Cons**: Single-process only, manual cleanup needed

## Compliance
- [ ] Backend: `app/services/sse.py` with in-memory queue dict
- [ ] Backend: Graph nodes call `emit_event(pipeline_run_id, event)`
- [ ] Backend: SSE endpoint `/morning-notes/{id}/stream` yields events
- [ ] Backend: Cleanup queue on `note_ready` or `pipeline_failed`
- [ ] Frontend: `useEventSource` hook with reconnection logic
- [ ] Frontend: `usePipelineSSE` hook parses events → `agentProgress`, `isComplete`, `error`
- [ ] Frontend: `PipelineSSE` component renders timeline with badges
- [ ] Frontend types: `SSEEvent` union in `src/api/types.ts`

## Notes
- Upgrade trigger: ECS tasks > 1 (multiple FastAPI workers)
- Event schema identical for Option C and B → zero frontend changes
- Related: ADR 012 (Detail Response), ADR 022 (Date/Time), ADR 024 (Testing)
- Review date: 2026-09-20 (before production deploy)

## References
- Phase 1+2 Plan: FE-4.1 through FE-4.6
- Backend SSE stub: `app/api/routes/morning_notes.py:41-53`
- Graph pipeline: `app/graph/pipeline.py:25-37`
- Frontend types: `src/api/types.ts` (SSEEvent union)