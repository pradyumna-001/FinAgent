from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from app.api.deps import get_current_manager
from app.db.models import Manager, Portfolio, PortfolioHolding
from app.db.session import SessionLocal
from app.schemas.pipeline import TriggerRequest, TriggerResponse

# run_pipeline_for_portfolio will be imported after Step 10

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pipeline(
    payload: TriggerRequest,
    background: BackgroundTasks,
    manager: Annotated[Manager, Depends(get_current_manager)],
) -> JSONResponse:
    """Trigger a multi-ticker pipeline run for a portfolio.

    Validates portfolio ownership, counts tickers, and dispatches
    the pipeline to the Celery worker via background task.

    Args:
        payload: TriggerRequest with manager_id and portfolio_id.
        background: FastAPI BackgroundTasks for async dispatch.
        manager: Authenticated manager from JWT (dependency).

    Returns:
        JSONResponse with pipeline_run_id, morning_note_id, portfolio_id,
        tickers_count, and status="pending".

    Raises:
        HTTPException: 404 if portfolio not found or not owned by manager.
    """

    async with SessionLocal() as session:
        await session.execute(text("SET LOCAL app.manager_id = :mid"), {"mid": manager.id})

        result = await session.execute(
            select(Portfolio).where(
                Portfolio.id == payload.portfolio_id,
                Portfolio.manager_id == manager.id
            )
        )
        portfolio = result.scalar_one_or_none()
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found"
            )

        ticker_count = await session.execute(
            select(func.count(PortfolioHolding.id)).where(
                PortfolioHolding.portfolio_id == payload.portfolio_id
            )
        )
        tickers_count = ticker_count.scalar() or 0

    response = TriggerResponse(
        portfolio_id=payload.portfolio_id,
        tickers_count=tickers_count
    )

    # Will import run_pipeline_for_portfolio in Step 10
    # background.add_task(
    #     run_pipeline_for_portfolio,
    #     manager_id=manager.id,
    #     portfolio_id=payload.portfolio_id,
    #     pipeline_run_id=str(response.pipeline_run_id),
    #     morning_note_id=str(response.morning_note_id)
    # )

    # For now, keep stub to avoid breaking - will replace in Step 10
    from app.services.pipeline import run_pipeline_stub
    background.add_task(
        run_pipeline_stub,
        str(response.pipeline_run_id),
        str(response.morning_note_id)
    )

    return JSONResponse(
        content=response.model_dump(mode="json"),
        status_code=status.HTTP_202_ACCEPTED,
        headers={"X-Pipeline-Run-Id": str(response.pipeline_run_id)},
    )
