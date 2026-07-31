import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_list_morning_notes_missing_header_returns_400() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes")
    assert resp.status_code == 400
    assert resp.json() == {"detail": "manager_id header required"}


@pytest.mark.asyncio
async def test_list_morning_notes_with_header_returns_list(
    migrated_db_url: str,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"manager-id": "2"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
