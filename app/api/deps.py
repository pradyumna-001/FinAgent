from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_read_session
from app.services.analysis import AnalysisService
from app.services.auth import AuthService
from app.core.security import decode_access_token
from app.api.errors import InvalidTokenError
from app.db.models import Manager


security = HTTPBearer(auto_error=False)


async def get_current_manager(
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
        session: Annotated[AsyncSession, Depends(get_read_session)]
) -> Manager:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if not payload or "manager_id" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    auth_service = AuthService(session)
    manager = await auth_service.get_by_id(payload["manager_id"])
    if not manager:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Manager not found")
    
    return manager


def get_analysis_service() -> AnalysisService:
    return AnalysisService(
        openai_client=None,
        market_data_client=None,
        news_client=None,
        db_session=None
    )
