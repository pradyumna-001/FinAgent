from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback
from app.db.session import get_session
from app.schemas.feedback import FeedbackCreate, FeedbackResponse



router = APIRouter(prefix="/morning-notes/{note_id}/feedback", tags=["feedback"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_feedback(
    note_id: int,
    payload: FeedbackCreate,
    manager_id: int | None = Header(None, alias="manager-id"),
    session: AsyncSession = Depends(get_session)
):
    if manager_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="manager_id header required")

    async with session.begin():
        await session.execute(
            text(f"SET LOCAL app.manager_id = '{manager_id}'")
        )
        result = await session.execute(
            text(
                "SELECT id FROM morning_notes "
                "WHERE id = :nid AND  manager_id = :mid"
            ), {"mid": manager_id, "nid": note_id}
        )
        row = result.first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Morning note not found")

        feedback = Feedback(
            morning_note_id=note_id,
            manager_id=manager_id,
            action=payload.action,
            justification=payload.justification,
            comment=payload.comment
        )

        session.add(feedback)
        await session.flush()
        return FeedbackResponse.model_validate(feedback)
