from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Manager
from app.utils.security import verify_password


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def authenticate(self, email: str, password: str) -> Manager | None:
        stmt = select(Manager).where(Manager.email == email)
        result = await self.session.execute(stmt)
        manager = result.scalar_one_or_none()

        if (
            manager and manager.password_hash and 
            verify_password(password, manager.password_hash)
        ): return manager
        return None

    async def get_by_id(self, manager_id: int) -> Manager | None:
        stmt = select(Manager).where(Manager.id == manager_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
