import asyncio
import logging

from app.core.context import current_morning_note_id, current_pipeline_run_id

logger = logging.getLogger(__name__)


_PIPELINE_REGISTRY: dict[str, str] = {}


async def run_pipeline_stub(pipeline_run_id: str, morning_note_id: str) -> None:
    """Stub pipeline executor for testing (deprecated).

    Sets pipeline context variables and simulates a short delay.
    Replaced by run_pipeline_for_portfolio which dispatches to Celery.

    Args:
        pipeline_run_id: Unique identifier for this pipeline run.
        morning_note_id: Morning note identifier (UUID from API).
    """
    token_run = current_pipeline_run_id.set(pipeline_run_id)
    token_note = current_morning_note_id.set(morning_note_id)
    try:
        logger.info("pipeline stub started")
        await asyncio.sleep(0.1)
        logger.info("pipeline stub finished")
    finally:
        current_pipeline_run_id.reset(token_run)
        current_morning_note_id.reset(token_note)


async def run_pipeline_for_portfolio(
    manager_id: int,
    portfolio_id: int,
    pipeline_run_id: str,
    morning_note_id: str
) -> None:
    """Dispatch the portfolio pipeline to Celery worker.

    Called by API background task after trigger validation.
    Sends task to Celery queue with all required parameters.

    Args:
        manager_id: Manager owning the portfolio.
        portfolio_id: Portfolio to generate morning note for.
        pipeline_run_id: Unique pipeline run identifier (from API).
        morning_note_id: Morning note identifier (UUID from API).
    """
    from app.workers.pipeline import celery_app

    celery_app.send_task(
        "app.workers.pipeline.run_daily_pipeline_for_portfolio",
        args=[manager_id, portfolio_id],
        kwargs={
            "pipeline_run_id": pipeline_run_id,
            "morning_note_id": morning_note_id,
        },
    )

