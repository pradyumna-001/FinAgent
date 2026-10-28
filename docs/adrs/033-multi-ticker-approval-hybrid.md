# ADR-033: Multi-Ticker Approval Gate — Hybrid Per-Ticker + Bulk Approval

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Pradyumna (solo)
**Related Issues**: #122 (multi-ticker morning notes), ADR-030 (schema), ADR-031 (AgentState), ADR-029 (approval gate)

---

## Context

Issue #122: One `MorningNote` per manager per portfolio, with `recommendations` JSONB containing per-ticker recommendations:
```json
{
  "PETR4": {"action": "buy", "confidence": 0.82, "justification": "..."},
  "VALE3": {"action": "keep", "confidence": 0.65, "justification": "..."},
  "ITUB4": {"action": "sell", "confidence": 0.71, "justification": "..."}
}
```

**Requirement**: Gestor must be able to:
- Approve/reject **individual tickers** (per-ticker granularity)
- Approve/reject **all at once** (bulk action for efficiency)
- Explicitly **submit** when done (avoids accidental resume)

Current `approval_gate_node` (ADR-029): Single interrupt, single recommendation, polls Telegram for one decision.

---

## Decision: Hybrid Approval Flow

### 1. Single LangGraph Interrupt (Unchanged Pattern)

```python
# app/agents/approval_gate.py
async def approval_gate_node(state: AgentState) -> dict:
    payload = {
        "recommendations": state["recommendations"],  # full dict keyed by ticker
        "morning_note_id": state["morning_note_id"],
        "pipeline_run_id": state["pipeline_run_id"],
        "manager_id": state["manager_id"],
    }
    decision = await interrupt(payload)  # PAUSES GRAPH
    # decision = {"PETR4": "approved", "VALE3": "rejected", "ITUB4": "approved"}
    
    # Persist per-ticker decisions to MorningNote.recommendations JSONB
    async with SessionLocal() as session:
        await session.execute(text("SET LOCAL app.manager_id = :mid"), {"mid": state["manager_id"]})
        mn = await session.get(MorningNote, int(state["morning_note_id"]))
        recommendations = mn.recommendations
        
        decided_at = datetime.now(UTC).isoformat()
        for ticker, mgr_decision in decision.items():
            if ticker in recommendations:
                recommendations[ticker]["manager_decision"] = mgr_decision
                recommendations[ticker]["decided_at"] = decided_at
                recommendations[ticker]["decision_channel"] = "telegram"
        
        mn.recommendations = recommendations
        mn.status = MorningNoteStatus.COMPLETED
        await session.flush()
    
    return {
        "manager_decisions": decision,
        "decided_at": datetime.now(UTC),
        "decision_channel": "telegram",
        "data_freshness": {"approval_gate": datetime.now(UTC)},
        "flags": []
    }
```

### 2. Telegram Message — Per-Ticker + Bulk + Submit

```
Morning Note — 2026-10-28

PETR4: BUY (82%)
  Strong earnings, macro tailwinds...
  [✅ Approve] [❌ Reject]

VALE3: KEEP (65%)
  Mixed China data, valuation fair...
  [✅ Approve] [❌ Reject]

ITUB4: SELL (71%)
  Credit quality concerns...
  [✅ Approve] [❌ Reject]

──────────────────
[✅ Approve All] [❌ Reject All]
[📤 Submit Decisions]
```

**Inline keyboard structure**:
```python
keyboard = []
for ticker in recommendations:
    keyboard.append([
        InlineKeyboardButton(f"✅ {ticker}", callback_data=f"appr_{ticker}"),
        InlineKeyboardButton(f"❌ {ticker}", callback_data=f"rej_{ticker}")
    ])
keyboard.append([
    InlineKeyboardButton("✅ Approve All", callback_data="appr_all"),
    InlineKeyboardButton("❌ Reject All", callback_data="rej_all")
])
keyboard.append([InlineKeyboardButton("📤 Submit", callback_data="submit")])
```

### 3. Poller — Redis Accumulator + Explicit Resume

```python
# app/workers/telegram_poller.py
async def handle_callback(query: CallbackQuery):
    data = query.data
    run_id, rec_id = extract_from_message(query.message)
    redis_key = f"decision:{run_id}:{rec_id}"
    
    decisions = json.loads(await redis.get(redis_key) or "{}")
    all_tickers = get_all_tickers_from_message(query.message)
    
    if data == "appr_all":
        decisions = {t: "approved" for t in all_tickers}
    elif data == "rej_all":
        decisions = {t: "rejected" for t in all_tickers}
    elif data.startswith("appr_"):
        decisions[data[5:]] = "approved"
    elif data.startswith("rej_"):
        decisions[data[4:]] = "rejected"
    elif data == "submit":
        # RESUME GRAPH with complete decisions
        config = {"configurable": {"thread_id": run_id}}
        await saver.aput(config, Command(resume=decisions))
        await query.answer("Decisões enviadas!")
        return
    
    await redis.set(redis_key, json.dumps(decisions), ex=86400)
    await update_message_buttons(query.message, decisions, all_tickers)
    await query.answer(f"{ticker}: {decision}")
```

**Key behaviors**:
- **No auto-resume** — only "Submit" button triggers `Command(resume=...)`
- **Bulk buttons overwrite** — "Approve All" sets all tickers to approved
- **Per-ticker toggles** — clicking same button twice could toggle (optional)
- **Visual feedback** — buttons update to show current selection (✅/❌/⏳)

### 4. JSONB Schema Extension (Per-Ticker Decision Fields)

```json
{
  "PETR4": {
    "action": "buy",
    "confidence": 0.82,
    "justification": "...",
    "manager_decision": "approved",
    "decided_at": "2026-10-28T12:34:56Z",
    "decision_channel": "telegram"
  },
  "VALE3": {
    "action": "keep",
    "confidence": 0.65,
    "justification": "...",
    "manager_decision": "rejected",
    "decided_at": "2026-10-28T12:35:10Z",
    "decision_channel": "telegram"
  }
}
```

### 5. Finalize Node — Validates All Decided

```python
# app/agents/finalize.py
async def finalize_morning_note_node(state: AgentState) -> dict:
    decisions = state.get("manager_decisions", {})
    recommendations = state.get("recommendations", {})
    
    # Check all tickers have a decision
    undecided = [t for t in recommendations if t not in decisions]
    if undecided:
        # Should not happen if Submit button used, but guard anyway
        return {
            "flags": [DataFlag(
                source="finalize",
                severity=Severity.WARNING,
                message=f"Tickers without decision: {undecided}"
            )],
            "data_freshness": {"finalize": datetime.now(UTC)}
        }
    
    return {
        "data_freshness": {"finalize": datetime.now(UTC)},
        "flags": []
    }
```

---

## Consequences

### Positive
- **Flexible UX** — gestor chooses granularity (per-ticker or bulk)
- **Single interrupt** — LangGraph pattern unchanged, no multiple resumes
- **Explicit submit** — prevents accidental resume from stray callback
- **Per-ticker audit trail** — `decided_at` per ticker, all in JSONB
- **Extensible** — future channels (Sheets, Calendar) add `decision_channel` per ticker

### Negative / Risks
- **Poller complexity** — Redis accumulator + button state sync + message editing
- **Telegram message size** — 10 tickers × 2 buttons = 20 buttons + 3 bulk = 23 buttons (within limits)
- **Race condition** — two callbacks simultaneously could overwrite; Redis `GET/SET` not atomic (mitigate with Lua script or `WATCH`)
- **No decision = incomplete** — if gestor never clicks Submit, note stays pending (add TTL cleanup job)

---

## Migration Path

1. **Update `send_note_node`** — build multi-ticker message with per-ticker + bulk buttons
2. **Update `approval_gate_node`** — payload = full recommendations dict; resume writes per-ticker decisions
3. **Update `telegram_poller.py`** — Redis accumulator, handle `appr_all`/`rej_all`/`submit`, update message buttons
4. **Update `finalize_morning_note_node`** — validate all tickers decided
5. **Test** — integration test with 3 tickers, simulate per-ticker + bulk + submit flow

---

## Testing

| Test | Scope |
|------|-------|
| `tests/integration/test_approval_gate_multi.py` | Gate receives per-ticker decisions, writes JSONB correctly |
| `tests/unit/test_telegram_poller_accumulator.py` | Redis accumulator handles bulk + per-ticker + submit |
| `tests/integration/test_approval_flow.py` | Full flow: interrupt → poller callbacks → submit → resume → finalize |
| `tests/unit/test_finalize_validation.py` | Finalize flags undecided tickers |

---

## Future Work

- **TTL cleanup job** — scan for pending notes > 24h, auto-reject or alert
- **Per-ticker `telegram_update_id`** — store in JSONB if needed for replay audit
- **Sheets/Calendar channels** — extend `decision_channel` per ticker
- **Partial approval semantics** — what does "completed" mean if some rejected? (Currently: all must have decision, status = completed)

---

## References

- ADR-029: Approval Gate (single-ticker baseline)
- ADR-030: Multi-Ticker Database Schema (`recommendations` JSONB)
- ADR-031: Multi-Ticker AgentState & Graph
- `app/agents/approval_gate.py` — current gate implementation
- `app/workers/telegram_poller.py` — current poller implementation
- `app/services/decisions.py` — Redis dedup logic (extends to accumulator)