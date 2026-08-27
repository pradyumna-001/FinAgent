import json

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import MorningNoteNotFound
from app.api.deps import get_current_manager
from app.db.session import get_session
from app.db.models import MorningNote, Manager
from app.services.pipeline import _PIPELINE_REGISTRY
from app.services.sse import sse_service


router = APIRouter(prefix="/morning-notes", tags=["morning-notes"])


@router.get("")
async def list_morning_notes(
    session: Annotated[AsyncSession, Depends(get_session)],
    manager: Annotated[Manager, Depends(get_current_manager)]
) -> list[dict]:
    manager_id = manager.id

    async with session.begin():
        await session.execute(
            text(f"SET LOCAL app.manager_id = '{int(manager_id)}'")
        )
        result = await session.execute(
            text(
                "SELECT id, generated_at, note_text, status FROM morning_notes "
                "WHERE manager_id = :mid ORDER BY generated_at DESC LIMIT 50"
            ), {"mid": manager_id},
        )

        return [dict(row._mapping) for row in result]


@router.get("/{note_id}/stream")
async def stream_morning_note(
    note_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    manager: Annotated[Manager, Depends(get_current_manager)]
):
    async with session.begin():
        stmt = select(MorningNote).where(
            MorningNote.id == note_id,
            MorningNote.manager_id == manager.id
        )
        result = await session.execute(stmt)
        note = result.scalar_one_or_none()

        if note is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Morning note not found")
        
    run_id = _PIPELINE_REGISTRY.get(note_id)
    if run_id is None:
        raise MorningNoteNotFound(note_id)

    async def event_stream():
        async for event in sse_service.subscribe(run_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/{note_id}")
async def read_morning_note(
    note_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    manager: Annotated[Manager, Depends(get_current_manager)]
) -> dict:
    manager_id = manager.id

    async with session.begin():
        await session.execute(
            text(f"SET LOCAL app.manager_id = '{int(manager_id)}'")
        )
        stmt = select(MorningNote).where(
            MorningNote.id == note_id,
            MorningNote.manager_id == manager_id,
        ).options(
            selectinload(MorningNote.recommendation),
            selectinload(MorningNote.manager),
            selectinload(MorningNote.company)
        )
        result = await session.execute(stmt)

        note = result.scalar_one_or_none()
        if note is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Morning note not found")

        response = {
            "id": note.id,
            "generated_at": note.generated_at,
            "note_text": note.note_text,
            "status": note.status,
            "confidence_scores": note.confidence_scores,
            "data_freshness": note.data_freshness,
            "flags": note.flags,
            "pipeline_run_id": note.pipeline_run_id,

            "recommendation": {
                "action": note.recommendation.action,
                "confidence": note.recommendation.confidence,
                "justification": note.recommendation.justification,
                "created_at": note.recommendation.created_at,
                "confirmed_at": note.recommendation.confirmed_at
            } if note.recommendation else None,

            "manager_name": note.manager.name,
            "company_ticker": note.company.ticker,
            "company_name": note.company.name
        }
        
    return response
