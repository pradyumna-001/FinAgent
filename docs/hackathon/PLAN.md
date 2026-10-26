# Implementation Plan

## What we will implement

1. **Telegram Delivery & Approval Adapter**
   - Channel adapter with protocol: send_note(), await_decision()
   - Inline keyboards per recommendation: ✅ aprovar / ❌ rejeitar
   - LangGraph interrupt after EditorAgent; resume on user tap

2. **Google Sheets Track Record**
   - Append-only sheet per manager: timestamp, company, recommendation, confidence, flags, gestor decision, latency
   - Sheets sync as idempotent best-effort replica of Postgres decisions

3. **Google Calendar Event Scheduler**
   - CompanyAgent already detects earnings, dividends, JCP, M&A dates
   - Create calendar events for gestor with context link to morning note

## How we will implement

### Telegram channel
`app/services/channels/base.py` defines Channel protocol.
`app/services/channels/telegram_channel.py` implements using python-telegram-bot long polling.

Long polling chosen for demo — no public URL required. Worker polls Telegram, matches message to `pipeline_run_id` in AgentState, injects approval back into LangGraph checkpoint.

DDIA: event ingestion with at-least-once semantics. We deduplicate approvals by `pipeline_run_id + recommendation_id`.

### Sheets sync
Post-commit hook after decision written to Postgres. Write row to Sheets via Google Sheets API. If write fails, enqueue to Celery retry queue; do not block decision.

DDIA Ch.5 replication: Sheets is downstream replica, eventually consistent, Postgres is source of truth.

### Calendar
CompanyAgent emits `temporal_events` in state. A side node `calendar_node` reads them and calls Google Calendar API to create events. Duplicate-safe using event idempotency key = `company + date + type`.

## Why these integrations

| Integration | Value to user | DDIA principle |
|-------------|---------------|----------------|
| Telegram | Meets gestor where they are (phone, 6 AM). Turns report into decision. | Ch.1 – Reliability of human feedback loop; Ch.7 – Long-running transactions with human participant |
| Sheets | Accountability & track record. CVM compliance requires audit trail. | Ch.5 – Replication; Ch.9 – Consistency: decision persists before side-effects |
| Calendar | Proactive scheduling. Agent acts, not just informs. | Ch.11 – Event-driven processing |

These three close the workflow:
Analyze → Deliver → Decide → Record → Evaluate

All three are external apps, all have clear product value beyond the hackathon requirement, and all preserve FinAgent's invariants: freshness, RLS isolation, fail-visible.
