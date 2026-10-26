# System & Reliability Brief — FinAgent Hackathon

## System Overview

FinAgent is a multi-agent LangGraph pipeline for Brazilian asset managers. Hackathon scope adds action layer across three external apps.

**External apps integrated:**
1. Telegram — delivery + human-in-the-loop approvals
2. Google Sheets — audit trail / track record replica
3. Google Calendar — proactive event scheduling

**Pipeline:** MacroAgent + CompanyAgent + QuantAgent + RiskAgent (parallel fan-out) → EditorAgent → interrupt for human approval via Telegram → decision persisted → Sheets + Calendar side-effects.

## How we know it works

### Reliability invariants (tested in CI, preserved)
1. Freshness — data_freshness stamped per domain; >24h → DataFlag
2. RLS Isolation — every query requires gestor_id; enforced at DB
3. Fail Visible — every failure appends DataFlag; pipeline never silent

DDIA Ch.1: reliability over scale.

### Evaluation strategy
- **Unit tests**: Telegram channel protocol, Sheets idempotent writes, Calendar duplicate detection
- **Integration tests**: full pipeline with mocked Telegram updates; verify Postgres decision recorded before Sheets write
- **Reliability demo**: induce Tavily/yfinance failure → DataFlag appears in Telegram note; pipeline completes
- **Metrics captured in Sheets**: recommendation timestamp, confidence, flags, gestor decision latency, approval rate

### Consistency & failure modes
- Source of truth: Postgres
- Sheets/Calendar are downstream replicas, best-effort with Celery retry
- Approvals idempotent by pipeline_run_id + recommendation_id
- Channel failures append WARN DataFlag, do not block persistence

DDIA Ch.5 replication, Ch.7 transactions, Ch.9 consistency

## Demo flow (2 min)
1. Trigger pipeline
2. LangSmith trace shows parallel fan-out
3. Telegram message arrives with inline buttons
4. Approve → pipeline resumes, row appears in Sheets, calendar event created
5. Show DataFlag handling on simulated data failure

## Risks & mitigations
- Telegram opt-in friction → demo bot pre-created, judge chats /start first
- Sheets API rate limits → batch appends, exponential backoff
- Long-running interrupt timeout → checkpoint persists state, resumes on next update
