from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.auth import AuthService
from app.core.security import create_access_token
from app.api.deps import get_current_manager
from app.db.models import Manager


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    manager: dict


@router.post("/login")
async def login(
    data: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)]
) -> TokenResponse:
    auth_service = AuthService(session)
    manager = await auth_service.authenticate(data.email, data.password)
    if not manager:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": manager.email, "manager_id": manager.id})
    return TokenResponse(
        access_token = token,
        manager = {
            "id": manager.id,
            "name": manager.name,
            "email": manager.email
        }
    )


@router.get("/me")
async def me(current_manager: Annotated[Manager, Depends(get_current_manager)]) -> dict:
    return {
        "id": current_manager.id,
        "name": current_manager.name,
        "email": current_manager.email
    }
