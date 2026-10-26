# Architecture

## Data flow

```
Celery Beat 6:00 AM
      ↓
LangGraph pipeline
 MacroAgent | CompanyAgent | QuantAgent | RiskAgent (parallel fan-out)
      ↓
 EditorAgent → morning_note + recommendations
      ↓
 [INTERRUPT] → Telegram Channel sends note with inline buttons
      ↓ (gestor taps)
 Resume pipeline with approvals in AgentState
      ↓
 Postgres: decision persisted with gestor_id, timestamp
      ↓ (side-effects)
 Google Sheets ← append row (track record)
 Google Calendar ← create events from temporal_events
```

## State changes

AgentState additions:
```
approvals: dict[str, Literal["approved","rejected","pending"]]
telegram_message_id: str
channel: ChannelProtocol
```

Reducers keep `flags` and `data_freshness` merging from parallel agents.

## Reliability considerations — DDIA

- **Freshness invariant**: every external read stamps `data_freshness`. Telegram/Sheets/Calendar writes do not affect freshness, only delivery.
- **Fail-visible**: channel failures append DataFlag(severity=WARN), pipeline continues, note delivered later via retry.
- **Idempotency**: approval webhook is idempotent by `(pipeline_run_id, recommendation_id)`. Duplicate taps ignored.
- **Source of truth**: Postgres. Sheets/Calendar are replicas. Write path: Postgres → emit → replica. Never read from replica for decision.
- **Long-running transaction**: interrupt/resume keeps correlation ids in place. Logs include X-Pipeline-Run-Id, X-Morning-Note-Id.

## Demo story

1. Trigger pipeline manually.
2. Show LangSmith trace with parallel fan-out.
3. Telegram message arrives on phone with recommendations and buttons.
4. Tap approve → pipeline resumes, Postgres updated.
5. Google Sheets opens, new row appears.
6. Calendar shows new earnings event.

Reliability shown by flags appearing when a data source fails, note still delivered.
