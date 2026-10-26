# Hackathon Plan — FinAgent Lite

## Deadline: 9:30 AM – 4:00 PM (6.5 hours)
## Goal: Working 2-min demo with 3 external app integrations

---

## PHILOSOPHY: Minimum Viable Hackathon Submission
- Reuse existing LangGraph pipeline (no agent reimplementation)
- Mock LLM for deterministic synthetic data (save 2+ hours)
- Google Service Account auth (no OAuth consent screen)
- Telegram in "demo mode" (log instead of real messaging)
- **Goal:** Working demo + submission docs, not production system

---

## COMPRESSED TIMELINE (6h 30m)

| Milestone | Duration | Key Deliverable |
|-----------|----------|-----------------|
| **M1: Foundation** | 45 min | Scaffold + synthetic end-to-end test passes |
| **M2: Telegram** | 60 min | Bot sends note + inline buttons; demo mode callback |
| **M3: Google Sheets** | 45 min | Service account auth + append-row (7-column schema) |
| **M4: Google Calendar** | 45 min | Service account event creation + idempotency |
| **M5: Integration** | 60 min | Editor → Telegram gate → Sheets + Calendar fan-out |
| **M6: Demo & Submission** | 45 min | `scripts/demo.sh` (<2 min) + SUBMISSION.md + recording |
| **M7: Polish** | 30 min | Lint, typecheck, git clean, submission package |

**Total: 6h 30m (9:30 AM – 4:00 PM)**

---

## M1: Foundation — Scaffold + Synthetic E2E (45 min)

### Actions
- [ ] Verify existing dev graph compiles: `uv run python -c "from app.graph.pipeline import dev_graph; print('OK')"`
- [ ] Create `tests/test_pipeline.py` with `synthetic_state()` fixture
- [ ] Create `app/main.py` CLI entry point: `python app/main.py --ticker PETR4`
- [ ] Create `app/.env.example` with `TAVILY_API_KEY=dummy`, `NVIDIA_API_KEY=dummy`
- [ ] Create `app/services/llm_mock.py` — returns deterministic JSON (morning_note + recommendation + confidence_scores)

### Files
- `tests/test_pipeline.py` — unit test running pipeline on synthetic state
- `app/main.py` — CLI trigger
- `app/.env.example` — placeholder env vars
- `app/services/llm_mock.py` — deterministic mock (CRITICAL for time)

### Success
- `pytest tests/test_pipeline.py -v` passes
- `python app/main.py --ticker PETR4` generates morning note from synthetic data

---

## M2: Telegram — Bot + Inline Buttons (60 min)

### Actions
- [ ] Create `app/services/channels/telegram_channel.py`
- [ ] Inline keyboards: `[✅ Aprovar]` / `[❌ Rejeitar]` with callback data `approve|REJECT|pipeline_run_id|rec_id`
- [ ] `send_note()` — demo mode: log `"sent to Telegram"` + print ASCII QR code
- [ ] `await_decision(pipeline_run_id, timeout=300)` — demo mode: auto-approve after 2s, or wait for callback
- [ ] No real bot token needed for M1-M5; token only used in M6 demo

### Files
- `app/services/channels/telegram_channel.py` — new file

### Success
- `send_note()` logs message sent (no API call needed until demo day)
- `await_decision()` returns `("approved", message_id)` or `("rejected", message_id)`

---

## M3: Google Sheets — Service Account + Append-Row (45 min)

### Actions
- [ ] Download GCP Service Account JSON key from Cloud Console
- [ ] Create new Google Sheet → share with judge email → get `SHEETS_SPREADSHEET_ID`
- [ ] Use `gspread` with service account credentials
- [ ] Append row: `[timestamp, company_ticker, action, confidence, flag_sources, gestor_decision, latency_ms]`
- [ ] Idempotency: write key = `(pipeline_run_id, recommendation_id)`; skip if row exists
- [ ] Error handling: retry with backoff; **never block pipeline**

### Files
- `app/services/sheets.py` — new file

### Success
- Row appended to Google Sheet with 7-column schema
- Duplicate writes ignored on re-run

---

## M4: Google Calendar — Event Creation (45 min)

### Actions
- [ ] Auth: Service account with impersonation (`sub = manager's Google email`)
  - *Faster than OAuth — no consent screen, no refresh token flow*
- [ ] Create event: title = `📊 {action}: {ticker} — {event_type}`; date = from `company_events`; description = link to Postgres morning note
- [ ] Idempotency key: `f"{ticker}_{date}_{type}"` — skip if event already exists
- [ ] Fallback: if API fails → `DataFlag(severity=WARNING)`; pipeline continues

### Files
- `app/services/calendar.py` — new file

### Success
- Calendar event created with title/date/description
- Duplicate events skipped on re-run

---

## M5: Integration — Approval Gate + Fan-Out (60 min)

### Changes to Existing
- **`app/graph/pipeline.py`**: Add `telegram` node between `editor` and `END`:
  ```python
  builder.add_edge("editor", "telegram")
  builder.add_edge("telegram", END)
  ```
- **Generate `recommendation_id`** after `editor_agent_node` succeeds (UUID; include in state)

### Actions
- [ ] On `approve` → fan-out in parallel: `asyncio.gather(append_decision(), create_events())`
- [ ] On `reject` → only record decision in Postgres; no Sheets/Calendar writes
- [ ] If Sheets/Calendar fail → append `DataFlag(severity=WARNING)`; pipeline completes
- [ ] Persist `gestor_decision` and `decision_timestamp` to AgentState → Postgres

### Success
- Pipeline: editor → Telegram interrupt → operator taps button → Sheets row + Calendar event created
- On failure: DataFlag appears, but pipeline completes (fail-visible)

---

## M6: Demo & Submission (45 min)

### Actions
- [ ] Create `scripts/demo.sh` — times out at 2 min; runs pipeline → shows "sent to Telegram" → simulates tap → shows Sheets row → shows Calendar event
- [ ] Prepare LangSmith trace screenshot (parallel fan-out from existing pipeline)
- [ ] Write reliability brief (3 invariants: freshness, RLS isolation, fail-visible)
- [ ] Write `SUBMISSION.md` using `docs/hackathon/` templates
- [ ] Record 2-min screen capture (OBS → upload to Loom/YouTube unlisted)

### Files
- `scripts/demo.sh` — bash demo script (max 2 min)
- `docs/hackathon/SUBMISSION.md` — submission brief
- Updated `README.md`

### Success
- `scripts/demo.sh` runs end-to-end in <2 minutes
- Submission docs cover all 5 evaluation criteria (30% judging, 25% technical, 20% reliability, 15% usefulness, 10% originality, 10% demo clarity)

---

## M7: Polish & Buffer (30 min)

### Actions
- [ ] `uv run ruff check .` — fix lint issues
- [ ] `uv run mypy app` — fix type errors
- [ ] `git status` — ensure no secrets committed (especially service account JSON!)
- [ ] Final submission package (ZIP or git tag `hackathon-submission`)

### Success
- Code passes lint + typecheck
- Repo in clean state for submission

---

## KEY TIME-SAVING INSIGHTS

| Risk | Mitigation |
|------|------------|
| LLM unreliability | `llm_mock.py` — deterministic JSON from Day 1 |
| Telegram API friction | Demo mode until actual demo; real bot only in M6 |
| Google OAuth flow | Service account with impersonation (1 file download, no consent) |
| Time overrun | Strict timeline; if M5 not done, demo script shows partial flow |
| Secrets in repo | `.gitignore` excludes `*.json`; never commit service account keys |

---

## EVALUATION CRITERIA COVERAGE

| Criteria | How It's Covered |
|----------|-----------------|
| **30% Judging** | Working demo; 3 external apps; reliability story |
| **25% Technical execution** | LangGraph pipeline; service accounts; async fan-out |
| **20% Reliability & evaluation** | DataFlags; idempotency; fail-visible design |
| **15% Usefulness** | Calendar events; Sheets audit trail; Telegram decision capture |
| **10% Originality** | FinAgent → closed-loop analyst (novel for this hackathon) |
| **10% Demo clarity** | `scripts/demo.sh` (2 min); SUBMISSION.md; LangSmith trace |

---

## STOP CONDITION

You are ready to implement tomorrow at 9:30 AM when:
- [ ] M1: `pytest tests/test_pipeline.py -v` passes on synthetic data
- [ ] M2: Telegram `send_note()` and `await_decision()` work (demo mode)
- [ ] M3: Google Sheet row appends with correct 7-column schema
- [ ] M4: Calendar event creates with title/date/description
- [ ] M5: Pipeline: editor → Telegram tap → Sheets + Calendar fan-out
- [ ] M6: `scripts/demo.sh` runs in <2 minutes end-to-end

---

**Saved:** `C:\Users\mayco\OneDrive\Documents\finAgent\HACKATON_PLAN.md`