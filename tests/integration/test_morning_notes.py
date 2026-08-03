from collections.abc import Iterator
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.session as db_session
from app.main import app


@pytest.fixture
def bound_engine(migrated_db_url: str) -> Iterator[None]:
    engine = create_async_engine(migrated_db_url, echo=False)
    db_session.engine = engine
    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    yield
    engine.sync_engine.dispose()


@pytest.mark.asyncio
async def test_list_morning_notes_missing_header_returns_400() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes")
    assert resp.status_code == 400
    assert resp.json() == {"detail": "manager_id header required"}


@pytest.mark.asyncio
async def test_list_morning_notes_with_header_returns_list(
    bound_engine: None,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"manager-id": "2"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
