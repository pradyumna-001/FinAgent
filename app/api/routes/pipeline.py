from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_manager
from app.db.models import Manager
from app.schemas.pipeline import TriggerRequest, TriggerResponse
from app.services.pipeline import run_pipeline_stub


router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pipeline(
    payload: TriggerRequest,
    background: BackgroundTasks,
    manager: Annotated[Manager, Depends(get_current_manager)],
) -> JSONResponse:
    manager_id = manager.id

    response = TriggerResponse()
    from app.services.pipeline import _PIPELINE_REGISTRY
    _PIPELINE_REGISTRY[str(response.morning_note_id)] = str(response.pipeline_run_id)
    background.add_task(
        run_pipeline_stub,
        str(response.pipeline_run_id),
        str(response.morning_note_id)
    )

    body = JSONResponse(
        content=response.model_dump(mode="json"),
        status_code=status.HTTP_202_ACCEPTED,
        headers={"X-Pipeline-Run-Id": str(response.pipeline_run_id)},
    )
    return body
