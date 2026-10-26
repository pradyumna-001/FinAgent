# TypeScript + React Learning Plan
**Integrated with your React course + our Phase 2 frontend v0**

---

## Phase 0: TypeScript Basics (2-3 hours, before React course)

| Session | Topics | Practice |
|---------|--------|----------|
| 0.1 | Types, inference, functions, interfaces | Type along in TS Playground |
| 0.2 | Generics, union types, narrowing | Write `type ApiResponse<T> = ...` |
| 0.3 | Utility types (`Partial`, `Pick`, `Omit`) | Transform a Pydantic model to TS |

**Resource**: Your TS course (0:00–2:00) at 1.5x, skip classes/enums.

---

## Phase 1: React Course + TS Translation (3-4 hours, parallel)

| Course Section | TS Translation Task | Output |
|----------------|---------------------|--------|
| Components/JSX/Props | Write `interface Props` for every component | `NavbarProps`, `HeroProps` |
| `useState` | Add `<Type>` to every `useState` | `useState<string[]>([])` |
| `useEffect` + fetch | Replace with `useQuery<Type>` (TanStack Query) | **Our pattern** |
| React Router | Type `useParams()`, `useNavigate()` | `useParams<{id: string}>` |
| Forms | Type `React.FormEvent<HTMLFormElement>` | `handleSubmit(e: React.FormEvent<HTMLFormElement>)` |
| Context | `createContext<Type \| null>(null)` | `AuthContext` |

**Rule**: Pause video → write TS version → continue.

---

## Phase 2: Our Frontend v0 (6 days) — **Real Learning**

| Day | Scaffold Task | TS Concept Reinforced |
|-----|---------------|----------------------|
| 1 | `npm create vite@latest frontend -- --template react-ts` + Tailwind + TanStack Query + Router | Project config, strict mode |
| 1 | `src/types/api.ts` — mirror Pydantic | Interfaces, generics, unions |
| 1 | `useEventSource` hook | Generic hook return types |
| 2 | `useMorningNotes` + `Dashboard` | `useQuery<MorningNoteListItem[]>` |
| 3 | `GET /morning-notes/{id}` + `NoteDetail` | Nested interfaces, optional fields |
| 4 | `usePipelineTrigger` + `PipelineSSE` | `useMutation`, SSE event types |
| 5 | `POST /feedback` + `FeedbackButton` | Form types, discriminated unions |
| 6 | Polish, build, lint | `tsc --noEmit`, ESLint rules |

---

## Daily Rhythm (During Phase 2)

| Time | Activity |
|------|----------|
| **Morning (1h)** | Watch 30min React course → translate to TS in editor |
| **Main (3-4h)** | Work on that day's Phase 2 chunk (load `junior-frontend-coder`) |
| **Evening (15min)** | `npm run build` → fix all TS errors → commit |

---

## TS Cheatsheet for This Project

```typescript
// Types you'll use daily
interface MorningNoteListItem { id: number; generated_at: string; note_text: string; status: string; }
interface MorningNoteDetail extends MorningNoteListItem { confidence_scores: ConfidenceScores; data_freshness: DataFreshness; flags: DataFlag[]; recommendation: Recommendation | null; }
type ConfidenceScores = Record<'macro'|'company'|'quant'|'risk'|'overall', number>;
interface DataFlag { source: string; severity: 'info'|'warning'|'fatal'; message: string; created_at: string; }
interface Recommendation { action: 'buy'|'sell'|'keep'; justification: string; confidence: number; }

// Hooks
const { data, isLoading } = useQuery<MorningNoteListItem[]>({ queryKey: ['notes', managerId], queryFn: fetchNotes });
const mutate = useMutation({ mutationFn: (vars: TriggerRequest) => triggerPipeline(vars) });
const { data: events } = useEventSource<PipelineEvent>(`/pipeline/${runId}/stream`);
```

---

## Milestones

| Milestone | Target | Verification |
|-----------|--------|--------------|
| TS basics done | Day 0 end | Can write `interface`, `type`, generics without lookup |
| React course done | Day 3 end | Can build component + hook + route from memory |
| Dashboard working | Day 2 end | `npm run build` clean, list renders |
| Note detail working | Day 3 end | Full note with flags, scores, rec displays |
| SSE pipeline working | Day 4 end | Real-time agent progress shows |
| Feedback submits | Day 5 end | POST succeeds, UI updates |
| v0 complete | Day 6 end | All builds pass, manual E2E works |

---

## Questions Before Starting

1. **Start date** — When do you want to begin Day 0 (TS basics)?
2. **Pacing** — 6 consecutive days, or spread over 2 weeks?
3. **Accountability** — Want daily check-ins, or only when stuck?
4. **React course schedule** — Which sections first? (I suggest: Components → Hooks → Router → Forms → Data Fetching)

---

**Ready to schedule Day 0?**