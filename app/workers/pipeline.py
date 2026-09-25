"""Celery application for FinAgent pipeline workers."""

import asyncio
from uuid import uuid4

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_process_shutdown

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from app.db.session import engine

from app.core.config import settings
from app.core.context import current_pipeline_run_id
from app.graph.pipeline import compile_graph
from app.graph.state import create_initial_state
from app.workers.exceptions import WorkerNotInitializedError


_loop: asyncio.AbstractEventLoop | None = None
_saver_cm = None
_saver: AsyncPostgresSaver | None = None
_graph: CompiledStateGraph | None = None


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

        dsn = str(engine.url).replace("postgresql+asyncpg://", "postgresql://")
        _saver_cm = AsyncPostgresSaver.from_conn_string(dsn)
        _saver = await _saver_cm.__aenter__()
        await _saver.setup()

    _loop.run_until_complete(_open())
    _graph = compile_graph(_saver)


@worker_process_shutdown.connect
def shutdown_pipeline_resources(**kwargs):
    _loop.run_until_complete(_saver_cm.__aexit__(None, None, None))
    _loop.close()


@celery_app.task(bind=True, ignore_result=True)
def run_daily_pipeline(self, manager_id: int, company_ticker: str) -> None:
    if _graph is None or _loop is None:
        raise WorkerNotInitializedError(...)

    pipeline_run_id = uuid4()
    morning_note_id = uuid4()
    token = current_pipeline_run_id.set(str(pipeline_run_id))
    try:
        initial = create_initial_state(
            manager_id=manager_id,
            company_ticker=company_ticker,
            pipeline_run_id=pipeline_run_id,
            morning_note_id=morning_note_id
        )
        _loop.run_until_complete(
            _graph.ainvoke(initial, config={"configurable": {"thread_id": str(pipeline_run_id)}})
        )
    finally:
        current_pipeline_run_id.reset(token)
