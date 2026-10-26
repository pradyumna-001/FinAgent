# ADR 022: Date/Time & Timezone — date-fns + date-fns-tz

## Status
Accepted

## Context
Backend returns all timestamps in UTC (ISO 8601). Frontend must display in BRT (UTC-3) for Brazilian users. Brazil has no DST since 2019, but IANA timezone `America/Sao_Paulo` handles history correctly.

## Decision
**Option A: date-fns + date-fns-tz** (tree-shakeable, IANA, immutable, TS-first).

## Consequences

### Positive
- Tree-shakeable (~4kb), IANA timezone (`America/Sao_Paulo`), immutable, TS-first
- Relative time in pt-BR via `date-fns/locale`
- SSR-safe, no globals

### Negative
- Two packages vs one (dayjs)
- Functional style (some prefer OO)

### Neutral
- Migration to dayjs/Luxon documented if needed

## Options Considered

### Option A: date-fns + date-fns-tz (Chosen)
**Pros**: Tree-shakeable, IANA, immutable, TS-first, SSR-safe
**Cons**: Two packages, functional style

### Option B: dayjs
**Pros**: Smaller, mutable API familiar, plugins
**Cons**: Mutable by default, plugin system overhead, global `dayjs.tz.setDefault`

### Option C: Luxon
**Pros**: Rich Interval/Duration API, immutable
**Cons**: ~12kb, wrapper objects, larger

### Option D: Native Intl
**Pros**: Zero deps
**Cons**: No DST handling, no relative time, manual offset fragile

## Compliance
- [ ] `npm install date-fns date-fns-tz`
- [ ] `src/utils/date.ts` with: `formatBRT`, `formatBRTSmart`, `brtToUTC`, `formatForPicker`, `formatConfidence`, `formatFreshness`
- [ ] Usage in Dashboard, NoteDetail, PipelineSSE, TriggerModal
- [ ] Tests for all format functions

## Notes
- Timezone: `America/Sao_Paulo` (handles DST history)
- Locale: `ptBR` for relative formatting
- Smart formatting: relative (< 1 week) → full datetime
- Related: ADR 012 (Detail), ADR 013 (SSE), ADR 021 (Forms), ADR 024 (Testing)
- Review date: 2026-09-20

## References
- date-fns: https://date-fns.org/
- date-fns-tz: https://github.com/marnusw/date-fns-tz
- IANA: https://www.iana.org/time-zones
- Brazil: America/Sao_Paulo (BRT, UTC-3, no DST since 2019)