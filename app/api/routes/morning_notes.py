from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session


router = APIRouter(prefix="/morning-notes", tags=["morning-notes"])


@router.get("")
async def list_morning_notes(
    session: Annotated[AsyncSession, Depends(get_session)],
    manager_id: int | None = Header(None, alias="manager-id"),
) -> list[dict]:
    if manager_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="manager_id header required")

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