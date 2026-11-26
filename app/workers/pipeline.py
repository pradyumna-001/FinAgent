"""Celery application for FinAgent pipeline workers."""

import asyncio
import logging
from datetime import date
from uuid import uuid4

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_process_shutdown
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.context import current_pipeline_run_id
from app.db.models import Manager, MorningNote, MorningNoteStatus, Portfolio
from app.db.session import SessionLocal
from app.db.session import engine as get_engine
from app.graph.pipeline import compile_graph
from app.graph.state import create_initial_state, create_initial_state_multi
from app.services.portfolio import get_portfolio_tickers
from app.workers.exceptions import WorkerNotInitializedError

_loop: asyncio.AbstractEventLoop | None = None
_saver_cm = None
_saver: AsyncPostgresSaver | None = None
_graph: CompiledStateGraph | None = None

logger = logging.getLogger(__name__)


# Create Celery app
celery_app = Celery(
    "finagent",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.pipeline"],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3000,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    beat_schedule={
        "run-daily-pipeline": {
            "task": "app.workers.pipeline.run_daily_pipeline",
            "schedule": crontab(hour=9, minute=0),  # 9 UTC = 6 AM BRT
        },
        "run-daily-pipelines-for-all-portfolios": {
            "task": "app.workers.pipeline.run_daily_pipelines_for_all_portfolios",
            "schedule": crontab(hour=9, minute=30),  # 9:30 UTC = 6:30 AM BRT
        },
    },
)


# Auto-discover tasks
celery_app.autodiscover_tasks(["app.workers"])


@celery_app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to verify Celery is working."""
    print(f"Request: {self.request!r}")


@worker_process_init.connect
def init_pipeline_resources(**kwargs):
    global _loop, _saver_cm, _saver, _graph

    _loop = asyncio.new_event_loop()

    async def _open():
        global _saver_cm, _saver

        dsn = str(get_engine().url).replace("postgresql+asyncpg://", "postgresql://")
        _saver_cm = AsyncPostgresSaver.from_conn_string(dsn)
        _saver = await _saver_cm.__aenter__()
        await _saver.setup()

    _loop.run_until_complete(_open())
    _graph = compile_graph(_saver)


@worker_process_shutdown.connect
def shutdown_pipeline_resources(**kwargs):
    _loop.run_until_complete(_saver_cm.__aexit__(None, None, None))
    _loop.close()

async def _dispatch_portfolio_pipelines() -> None:
    """Fetch all portfolios across all managers and dispatch pipeline for each."""
    async with SessionLocal() as session:
        result = await session.execute(select(Manager.id))
        manager_ids = [row[0] for row in result.all()]

    for manager_id in manager_ids:
        async with SessionLocal() as session:
            await session.execute(text(f"SET LOCAL app.manager_id = {manager_id}"))
            result = await session.execute(select(Portfolio.id).where(Portfolio.manager_id == manager_id))
            portfolio_ids = [row[0] for row in result.all()]

        for portfolio_id in portfolio_ids:
            pipeline_run_id = str(uuid4())
            morning_note_id = str(uuid4())
            celery_app.send_task(
                "app.workers.pipeline.run_daily_pipeline_for_portfolio",
                args=[manager_id, portfolio_id, pipeline_run_id, morning_note_id]
            )


@celery_app.task(bind=True, ignore_result=True)
def run_daily_pipelines_for_all_portfolios(self) -> None:
    """Periodic task: dispatch pipeline for all portfolios."""
    if _loop is None:
        raise WorkerNotInitializedError("The worker is not initialized because loop is None")
    _loop.run_until_complete(_dispatch_portfolio_pipelines())


@celery_app.task(bind=True, ignore_result=True)
def run_daily_pipeline(self, manager_id: int, company_ticker: str) -> None:
    if _graph is None or _loop is None:
        raise WorkerNotInitializedError("The worker is not initialized because graph or loop is None")

    pipeline_run_id = uuid4()
    morning_note_id = uuid4()
    token = current_pipeline_run_id.set(str(pipeline_run_id))
    try:
        initial = create_initial_state(
            manager_id=manager_id,
            company_ticker=company_ticker,
            pipeline_run_id=str(pipeline_run_id),
            morning_note_id=str(morning_note_id)
        )
        _loop.run_until_complete(
            _graph.ainvoke(initial, config={"configurable": {"thread_id": str(pipeline_run_id)}})
        )
    finally:
        current_pipeline_run_id.reset(token)


@celery_app.task(bind=True, ignore_result=True)
def run_daily_pipeline_for_portfolio(
    self,
    manager_id: int,
    portfolio_id: int,
    pipeline_run_id: str,
    _api_morning_note_id: str
) -> None:

    if _graph is None or _loop is None:
        raise WorkerNotInitializedError("The worker is not initialized because graph or loop is None")

    async def _run():
        tickers = await get_portfolio_tickers(portfolio_id, manager_id)
        if not tickers:
            logger.warning("portfolio_has_no_tickers", manager_id=manager_id, portfolio_id=portfolio_id)
            return

        async with SessionLocal() as session:
            await session.execute(text(f"SET LOCAL app.manager_id = {manager_id}"))

            existing = await session.execute(
                select(MorningNote.id).where(
                    MorningNote.manager_id == manager_id,
                    MorningNote.portfolio_id == portfolio_id,
                    func.date(MorningNote.generated_at) == date.today(),
                    MorningNote.status.in_([MorningNoteStatus.GENERATING, MorningNoteStatus.COMPLETED])
                )
            )

            if existing.scalar():
                logger.info("morning_note_exists_skip", manager_id=manager_id, portfolio_id=portfolio_id)
                return

            morning_note = MorningNote(
                manager_id=manager_id,
                portfolio_id=portfolio_id,
                pipeline_run_id=pipeline_run_id,
                status=MorningNoteStatus.GENERATING,
                note_text="",
                recommendations={},
                confidence_scores={},
                data_freshness={},
                flags=[],
            )

            session.add(morning_note)
            await session.flush()
            morning_note_id = morning_note.id

        initial = create_initial_state_multi(
            manager_id=manager_id,
            company_tickers=tickers,
            pipeline_run_id=pipeline_run_id,
            morning_note_id=str(morning_note_id)
        )

        await _graph.ainvoke(initial, config={"configurable": {"thread_id": pipeline_run_id}})

    token = current_pipeline_run_id.set(pipeline_run_id)

    try:
        _loop.run_until_complete(_run())
    finally:
        current_pipeline_run_id.reset(token)
