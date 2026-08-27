from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Header, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback, Manager
from app.api.deps import get_current_manager
from app.db.session import get_session
from app.schemas.feedback import FeedbackCreate, FeedbackResponse


router = APIRouter(prefix="/morning-notes/{note_id}/feedback", tags=["feedback"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_feedback(
    note_id: int,
    payload: FeedbackCreate,
    manager: Annotated[Manager, Depends(get_current_manager)],
    session: AsyncSession = Depends(get_session)
):
    manager_id = manager.id
    
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

        result = await session.execute(
            text(
            "SELECT morning_note_id FROM feedbacks "
            "WHERE morning_note_id = :nid AND manager_id = :mid AND "
            "action = :act AND justification = :jus AND "
            "(comment = :com OR (comment IS NULL AND :com IS NULL))"
            ), {
            "mid": manager_id, 
            "nid": note_id, 
            "act": payload.action.value, 
            "jus": payload.justification, 
            "com": payload.comment
            }
        )
        if result.first() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This feedback already exists.")

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
