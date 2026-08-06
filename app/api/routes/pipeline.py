from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.schemas.pipeline import TriggerRequest, TriggerResponse
from app.services.pipeline import run_pipeline_stub


router = APIRouter(prefix="/pipeline", tags=["pipeline"])

@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pipeline(
    payload: TriggerRequest,
    background: BackgroundTasks,
    manager_id: int | None = Header(None, alias="manager-id"),
) -> JSONResponse:
    if manager_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="manager-id header required",
        )

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
