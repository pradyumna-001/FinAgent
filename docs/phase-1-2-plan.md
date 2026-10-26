# FinAgent — Phase 1+2 Parallel Execution Plan

**Goal**: Complete infra hardening (#03b, #03c, #05d) + Frontend v0 (React + TS) → then start MAGMA (#16-18)

---

## Phase 1: Infra Hardening (Issues #03b, #03c, #05d)

### #03b — App Role Split + Dual DATABASE_URL (2.5 days)

| Task | Description | Files | Dependencies |
|------|-------------|-------|--------------|
| 03b-1 | Create migration: `finagent_app` role (NOSUPERUSER NOBYPASSRLS LOGIN), GRANT DML on 6 tables | `alembic/versions/xxx_app_role_split.py` | — |
| 03b-2 | Add `MIGRATION_DATABASE_URL` to settings | `app/core/config.py` | — |
| 03b-3 | Update `alembic/env.py` to read `MIGRATION_DATABASE_URL` for migrations | `alembic/env.py` | 03b-2 |
| 03b-4 | Update `app/db/session.py` engine to use `DATABASE_URL` (app role) | `app/db/session.py` | 03b-2 |
| 03b-5 | Update RLS integration tests to connect as `finagent_app` | `tests/integration/test_rls.py`, `tests/conftest.py` | 03b-1 |
| 03b-6 | Add behavioral probe: `finagent_app` cannot DROP/CREATE | `tests/integration/test_app_role.py` (new) | 03b-1 |

### #03c — HNSW Reindex Script (1.5 days, independent)

| Task | Description | Files | Dependencies |
|------|-------------|-------|--------------|
| 03c-1 | `scripts/reindex_hnsw.py` — drift detection (idx_scan/row count thresholds) | `scripts/reindex_hnsw.py` | — |
| 03c-2 | Implement `REINDEX INDEX CONCURRENTLY` + state table for idempotency | Same file | 03c-1 |
| 03c-3 | Add `--dry-run` and `--force` flags | Same file | 03c-2 |
| 03c-4 | Document cron (6h BRT = 9h UTC) in README/DEPLOYMENT.md | `docs/` | 03c-3 |
| 03c-5 | Integration test with testcontainers | `tests/integration/test_reindex_hnsw.py` | 03c-2 |

### #05d — CI Integration Tests with Postgres (1.5 days, needs #03b)

| Task | Description | Files | Dependencies |
|------|-------------|-------|--------------|
| 05d-1 | Add `services.postgres` with pgvector+AGE image to CI workflow | `.github/workflows/ci.yml` | #03b done |
| 05d-2 | Create CI init SQL: `CREATE EXTENSION vector, age;` | `.github/scripts/ci-init.sql` (new) | 05d-1 |
| 05d-3 | Run `alembic upgrade head` in CI job before tests | `.github/workflows/ci.yml` | 05d-1 |
| 05d-4 | Update integration test job to use service container URL | `.github/workflows/ci.yml` | 05d-1 |
| 05d-5 | Enable all integration tests (RLS, migration, pipeline, graph) | `.github/workflows/ci.yml` | 05d-3 |

---

## Phase 2: Frontend v0 (React + TypeScript) — 6 Days

### Day 1: Scaffold & Configuration

| Task | Description | Files |
|------|-------------|-------|
| FE-1.1 | `npm create vite@latest frontend -- --template react-ts` | `frontend/` |
| FE-1.2 | Install deps: `react-router-dom`, `@tanstack/react-query`, `tailwindcss`, `@tailwindcss/vite`, `eslint`, `prettier`, `typescript-eslint` | `frontend/package.json` |
| FE-1.3 | Configure Tailwind v4 (Vite plugin), `tsconfig.json`, `vite.config.ts`, ESLint/Prettier | Config files |
| FE-1.4 | Create `src/types/api.ts` — mirror Pydantic schemas | `frontend/src/types/api.ts` |
| FE-1.5 | Set up TanStack Query provider + React Router in `App.tsx` | `frontend/src/App.tsx` |
| FE-1.6 | Create generic `useEventSource` hook for SSE | `frontend/src/hooks/useEventSource.ts` |

### Day 2: Dashboard (List View)

| Task | Description | Files |
|------|-------------|-------|
| FE-2.1 | `useMorningNotes` hook: `useQuery` for GET /morning-notes | `frontend/src/hooks/useMorningNotes.ts` |
| FE-2.2 | `Dashboard` component: table/list with id, date, status, confidence (overall) | `frontend/src/components/Dashboard.tsx` |
| FE-2.3 | `DashboardPage`: layout + header + trigger button placeholder | `frontend/src/pages/DashboardPage.tsx` |
| FE-2.4 | Route `/` → DashboardPage | `App.tsx` |

### Day 3: Note Detail View

| Task | Description | Files |
|------|-------------|-------|
| FE-3.1 | **Backend**: Add `GET /morning-notes/{id}` returning full detail | `app/api/routes/morning_notes.py` |
| FE-3.2 | `useMorningNoteDetail` hook: `useQuery` for GET /morning-notes/{id} | `frontend/src/hooks/useMorningNotes.ts` |
| FE-3.3 | `NoteDetail` component: full text, recommendation, confidence scores (5 sections), DataFlags with severity badges | `frontend/src/components/NoteDetail.tsx` |
| FE-3.4 | `NoteDetailPage` + route `/notes/:id` | `frontend/src/pages/NoteDetailPage.tsx` |
| FE-3.5 | Link from Dashboard row → NoteDetailPage | `Dashboard.tsx` |

### Day 4: Pipeline Trigger + SSE View

| Task | Description | Files |
|------|-------------|-------|
| FE-4.1 | `usePipelineTrigger` hook: `useMutation` for POST /pipeline/trigger | `frontend/src/hooks/usePipeline.ts` |
| FE-4.2 | `TriggerButton` component: opens modal for portfolio/company selection, calls trigger | `frontend/src/components/TriggerButton.tsx` |
| FE-4.3 | `usePipelineSSE` hook: wraps `useEventSource` + parses agent events | `frontend/src/hooks/usePipeline.ts` |
| FE-4.4 | `PipelineSSE` component: real-time agent progress (macro → company/quant → risk → editor) | `frontend/src/components/PipelineSSE.tsx` |
| FE-4.5 | `PipelinePage` + route `/pipeline/:runId` | `frontend/src/pages/PipelinePage.tsx` |
| FE-4.6 | Connect TriggerButton → navigate to PipelinePage on success | `TriggerButton.tsx` |

### Day 5: Feedback Endpoint + Button

| Task | Description | Files |
|------|-------------|-------|
| FE-5.1 | **Backend**: Add `Feedback` SQLAlchemy model + migration | `app/db/models.py`, new migration |
| FE-5.2 | **Backend**: `POST /morning-notes/{id}/feedback` endpoint | `app/api/routes/feedback.py` (new) |
| FE-5.3 | `useFeedback` hook: `useMutation` for POST /feedback | `frontend/src/hooks/useFeedback.ts` |
| FE-5.4 | `FeedbackButton` component: modal with action select, justification, comment | `frontend/src/components/FeedbackButton.tsx` |
| FE-5.5 | Integrate `FeedbackButton` into `NoteDetail` | `NoteDetail.tsx` |

### Day 6: Polish & Verification

| Task | Description | Files |
|------|-------------|-------|
| FE-6.1 | Loading skeletons, error boundaries, toast notifications | Various |
| FE-6.2 | Responsive layout (mobile dashboard, detail view) | Tailwind classes |
| FE-6.3 | `npm run build` + `npm run lint` — verify clean | `frontend/` |
| FE-6.4 | Manual E2E test: trigger → SSE → note detail → feedback | — |
| FE-6.5 | Add frontend CI job: build + lint | `.github/workflows/ci.yml` |

---

## Phase 3: MAGMA (Issues #16-18) — Starts After Phase 1+2 Complete

| Issue | Scope | Est. |
|-------|-------|------|
| #16 | Paper study, clone MAGMA, run LoCoMo, architecture design in `docs/magma-notes.md` | 3-4 days |
| #17 | 4 AGE graphs (semantic, temporal, causal, entity) + unified `app/memory/magma.py` | 3-4 days |
| #18 | Policy-guided traversal (rules first, then RL) + EditorAgent integration + feedback loop | 4-5 days |

---

## Parallel Execution Schedule

```
WEEK 1
├── Mon-Wed: #03b (App role split + dual DATABASE_URL)
├── Thu-Fri: #03c (HNSW reindex script)  ← PARALLEL with #03b tail
│
WEEK 2
├── Mon:     #05d (CI integration tests)  ← NEEDS #03b DONE
├── Tue-Sun: Frontend v0 (6 days)         ← CAN START Tue (backend stable)
│
WEEK 3+
└── MAGMA (#16-18)                        ← AFTER CI GREEN + FRONTEND MERGED
```

**Critical Path**: #03b → #05d → CI green → Frontend merge → MAGMA

**Parallelizable**: #03c runs independently. Frontend Days 1-3 need only GET endpoints (already exist); Days 4-5 need new backend endpoints (can be built in parallel with frontend hooks).

---

## Branch Strategy

| Branch | Scope | Merge Target |
|--------|-------|--------------|
| `feature/03b-app-role-split` | #03b only | `main` (PR) |
| `feature/03c-hnsw-reindex` | #03c only | `main` (PR) |
| `feature/05d-ci-integration` | #05d only | `main` (PR) |
| `feature/frontend-v0` | All Phase 2 (FE-1 through FE-6) | `main` (PR) |

**Rationale**: Small, reviewable PRs. Frontend is one branch because it's a cohesive feature.

---

## Open Decisions (Need Confirmation)

1. **Tailwind v4** (new Vite plugin) or v3? v4 is faster but newer.
2. **Feedback table schema** — confirm:
   ```sql
   CREATE TABLE feedback (
     id SERIAL PRIMARY KEY,
     morning_note_id INT REFERENCES morning_notes(id),
     manager_id INT REFERENCES managers(id),
     action VARCHAR(16) NOT NULL CHECK (action IN ('buy','sell','keep')),
     justification TEXT NOT NULL,
     comment TEXT,
     created_at TIMESTAMPTZ DEFAULT NOW()
   );
   ```
3. **GET /morning-notes/{id} response** — include all fields: `note_text`, `confidence_scores`, `data_freshness`, `flags`, `recommendation`, `status`, `generated_at`, `manager_id`, `company_id`?
4. **SSE event format** — current stub sends one event. Real implementation needs: `agent_started`, `agent_completed`, `note_ready`, `pipeline_failed`. Confirm event schema.
5. **Frontend CI** — run on every PR? Or only on `feature/frontend-v0` merges?

---

## Definition of Done (Phase 1+2)

- [ ] All 3 infra PRs merged, CI green
- [ ] Frontend builds (`npm run build`), lints clean
- [ ] Manual E2E: trigger pipeline → see SSE progress → view note detail → submit feedback
- [ ] `docs/issues.md` updated: #03b, #03c, #05d, #30 (frontend v0) checked off
- [ ] No console errors, no TypeScript errors

---

## Next Steps

1. You confirm open decisions above
2. I create first issue branch: `feature/03b-app-role-split`
3. Begin implementation (load `junior-socratic-coder` for coding tasks)

---

**Ready to proceed?** Confirm the 5 open decisions and I'll start with #03b.