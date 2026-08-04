import asyncio
import logging

from app.core.context import (
    current_morning_note_id,
    current_pipeline_run_id
)

logger = logging.getLogger(__name__)


async def run_pipeline_stub(pipeline_run_id: str, morning_note_id: str) -> None:
    token_run = current_pipeline_run_id.set(pipeline_run_id)
    token_note = current_morning_note_id.set(morning_note_id)
    try:
        logger.info("pipeline stub started")
        await asyncio.sleep(0.1)
        logger.info("pipeline stub finished")
    finally:
        current_pipeline_run_id.reset(token_run)
        current_morning_note_id.reset(token_note)
