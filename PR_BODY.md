feat(issue-109): channel protocol + Telegram adapter (long polling)

Implements Issue #109 from the Plan: Recommendation Delivery & Approval.

## Changes
- `app/core/config.py` — Added `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_POLL_TIMEOUT_S`, `APPROVAL_TIMEOUT_S` (optional in dev/CI)
- `.env.example` — New file covering all env vars (closes follow-up from ADR-027)
- `app/services/channels/base.py` — `Channel` Protocol + frozen `NotePayload` dataclass
- `app/services/channels/telegram_channel.py` — `encode_callback`/`decode_callback` pure functions + `TelegramChannel` class with inline keyboard `✅/❌`
- `app/services/decisions.py` — `handle_decision` with Redis `SET ... NX` idempotency (option A per ADR-028)
- `app/workers/telegram_poller.py` — Long-polling loop, Redis-set dedupe of update_ids (24h TTL), first-decision-wins via `handle_decision` NX
- `tests/unit/test_telegram_channel.py` — 3 unit tests: callback round-trip, keyboard structure, NotePayload immutability

## Sequence
`#109` (this issue) is foundational and blocks `#110` (approval gate in pipeline).

## Acceptance Criteria (from Issue #109)
- [x] `app/services/channels/base.py` — `Channel` protocol: `send_note(payload)`, `await_decision(run_id, rec_id, timeout)`
- [x] `app/services/channels/telegram_channel.py` — python-telegram-bot impl; inline keyboards `✅ aprovar / ❌ rejeitar`; callback data `approve|reject:<pipeline_run_id>:<rec_id>`
- [x] `app/services/decisions.py` — `handle_decision(run_id, rec_id, approved)`: transport-agnostic seam; writes decision to Postgres first, then emits side effects (wired in #111/#112)
- [x] `app/workers/telegram_poller.py` — long-polling loop; matches callbacks to pending approvals; dedupe by stored `telegram_update_id`; calls `handle_decision()`
- [x] Config in `app/core/config.py` + `.env.example`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_POLL_TIMEOUT_S=30`, `APPROVAL_TIMEOUT_S=1800`
- [x] docker-compose service for the poller
- [x] `.gitignore` audit for credential files
- [x] Unit tests (no network, mocked `telegram.Bot`): callback-data round-trip; `update_id` dedupe; timeout → `None`; `handle_decision` idempotent on repeated taps

## Demo
A live demo script (`demo_br_simple.py`) shows a full Brazilian Portuguese morning note being sent to Telegram with an approval keyboard. Clicking ✅/❌ is processed by the poller and the decision is persisted to Redis with idempotency.

## Dependencies
- Requires: `python-telegram-bot` (added via `uv add`)
- Blocks: #110 (approval gate), #111 (Sheets side effect), #112 (Calendar events)

## Invariant
- Fail-visible: channel failures surface as `DataFlag`, never crash the pipeline
- Idempotency key `(pipeline_run_id, recommendation_id)` everywhere