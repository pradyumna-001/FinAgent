from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine = None
_session_factory = None


def _get_engine():
    """Lazy singleton async engine for the application database.

    Creates the engine on first call and reuses it thereafter.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.DATABASE_URL, echo=False)
    return _engine


def _get_session_factory():
    """Lazy singleton async session factory bound to the application engine.

    Returns an async_sessionmaker configured with expire_on_commit=False.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a read-write AsyncSession from the application session factory."""
    factory = _get_session_factory()
    async with factory() as session:
        yield session


async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a read AsyncSession from the application session factory."""
    factory = _get_session_factory()
    async with factory() as session:
        yield session


def SessionLocal():
    """Backward-compatible callable that returns a new AsyncSession.

    Calls the session factory and invokes it to produce a fresh session.
    """
    return _get_session_factory()()


def engine():
    """Return the lazy singleton async engine (property-like accessor)."""
    return _get_engine()
