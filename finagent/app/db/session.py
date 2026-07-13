import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

logger = logging.getLogger("finagent")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://finagent:finagent_secure_pass@localhost:5432/finagent")

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider yielding a scoped database session"""
    session = AsyncSessionFactory()
    try:
        yield session
    except Exception as e:
        logger.error(f"Database transaction errror, rolling back: {str(e)}")
        await session.rollback()
        raise
    finally:
        await session.close()

async def set_tenant_context(session: AsyncSession, manager_id: int) -> None:
    """Injects the current manager_id into the PostgreSQL transaction state for RLS evaluation."""
    await session.execute(
        text("SELECT set_config('app.current_manager_id', :manager_id, true);"),
        {"manager_id": str(manager_id)}
    )
