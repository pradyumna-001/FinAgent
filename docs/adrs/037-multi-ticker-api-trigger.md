# ADR-037: Multi-Ticker API Trigger — Request/Response Schema

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Pradyumna (solo)
**Related Issues**: #122 (multi-ticker morning notes), ADR-030 (schema), ADR-031 (AgentState), ADR-034 (worker)

---

## Context

Current API trigger (single-ticker):
```python
# POST /pipeline/trigger
# Request: {manager_id, portfolio_id, company_id}
# Response: {pipeline_run_id, morning_note_id, status: "pending"}
```

Multi-ticker: One pipeline run per **manager + portfolio** (not per company). Single `MorningNote` created covering all portfolio tickers.

---

## Decision

### `TriggerRequest` — Remove `company_id`

```python
# app/schemas/pipeline.py

class TriggerRequest(BaseModel):
    manager_id: int
    portfolio_id: int
    # company_id: REMOVED
```

### `TriggerResponse` — Add Portfolio Context

```python
# app/schemas/pipeline.py

class TriggerResponse(BaseModel):
    pipeline_run_id: UUID = Field(default_factory=uuid4)
    morning_note_id: UUID = Field(default_factory=uuid4)
    portfolio_id: int              # NEW: which portfolio
    tickers_count: int             # NEW: how many tickers in portfolio
    status: Literal["pending"] = "pending"
```

### API Route — Fetch Ticker Count

```python
# app/api/routes/pipeline.py

@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pipeline(
    payload: TriggerRequest,
    background: BackgroundTasks,
    manager: Annotated[Manager, Depends(get_current_manager)],
) -> JSONResponse:
    
    # Verify portfolio belongs to manager
    async with SessionLocal() as session:
        result = await session.execute(
            select(Portfolio).where(
                Portfolio.id == payload.portfolio_id,
                Portfolio.manager_id == manager.id
            )
        )
        portfolio = result.scalar_one_or_none()
        if not portfolio:
            raise HTTPException(404, "Portfolio not found")
        
        # Count tickers for response
        ticker_count = await session.execute(
            select(func.count(PortfolioHolding.id))
            .where(PortfolioHolding.portfolio_id == payload.portfolio_id)
        )
        tickers_count = ticker_count.scalar() or 0
    
    response = TriggerResponse(
        portfolio_id=payload.portfolio_id,
        tickers_count=tickers_count
    )
    
    # Background task triggers worker (see ADR-034)
    background.add_task(
        run_pipeline_for_portfolio,
        manager_id=manager.id,
        portfolio_id=payload.portfolio_id,
        pipeline_run_id=str(response.pipeline_run_id),
        morning_note_id=str(response.morning_note_id)
    )
    
    return JSONResponse(
        content=response.model_dump(mode="json"),
        status_code=status.HTTP_202_ACCEPTED,
        headers={"X-Pipeline-Run-Id": str(response.pipeline_run_id)}
    )
```

### Background Task (Replaces `run_pipeline_stub`)

```python
# app/services/pipeline.py

async def run_pipeline_for_portfolio(
    manager_id: int,
    portfolio_id: int,
    pipeline_run_id: str,
    morning_note_id: str
) -> None:
    """Called by API background task. Dispatches to Celery worker."""
    from app.workers.pipeline import celery_app
    
    celery_app.send_task(
        "app.workers.pipeline.run_daily_pipeline_for_portfolio",
        args=[manager_id, portfolio_id],
        kwargs={
            "pipeline_run_id": pipeline_run_id,
            "morning_note_id": morning_note_id
        }
    )
```

---

## Consequences

### Positive
- **Clean request** — no `company_id` confusion
- **Informative response** — client knows portfolio + ticker count immediately
- **Single `morning_note_id`** — matches single note per portfolio
- **Backward compatible** — additive fields, no breaking changes for clients ignoring new fields

### Negative / Risks
- **API validates portfolio ownership** — adds DB query to trigger endpoint (fast, indexed)
- **Ticker count may change** — between trigger and worker execution (acceptable; response is snapshot)

---

## Migration Path

1. **Update `app/schemas/pipeline.py`** — new request/response models
2. **Update `app/api/routes/pipeline.py`** — fetch ticker count, pass to background task
3. **Update `app/services/pipeline.py`** — new `run_pipeline_for_portfolio` dispatches to Celery
4. **Update worker task signature** — accept `pipeline_run_id`, `morning_note_id` (ADR-034)
5. **Test** — API trigger returns correct portfolio_id, tickers_count

---

## Testing

| Test | Scope |
|------|-------|
| `tests/integration/test_api_trigger_multi.py` | Trigger request without company_id returns portfolio_id + tickers_count |
| `tests/unit/test_trigger_schema.py` | Schema validation rejects company_id, accepts portfolio_id |
| `tests/integration/test_background_task.py` | Background task dispatches Celery task with correct args |

---

## References

- ADR-030: Multi-Ticker Database Schema
- ADR-031: Multi-Ticker AgentState & Graph
- ADR-034: Multi-Ticker Persist Node (worker creates MorningNote)
- `app/schemas/pipeline.py` — current schemas
- `app/api/routes/pipeline.py` — current trigger endpoint
- `app/services/pipeline.py` — current `run_pipeline_stub`