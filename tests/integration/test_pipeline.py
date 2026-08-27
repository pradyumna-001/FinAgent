import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app


def _make_token(manager_id: int) -> str:
    return create_access_token({"sub": str(manager_id), "manager_id": manager_id})


@pytest.mark.asyncio
async def test_trigger_returns_202_with_ids(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/pipeline/trigger",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
            json={
                "manager_id": 2,
                "portfolio_id": 42,
                "company_id": 7,
            },
        )
    assert resp.status_code == 202
    body = resp.json()
    assert resp.headers["x-pipeline-run-id"] == body["pipeline_run_id"]
    assert body["status"] == "pending"
    assert len(body["morning_note_id"]) == 36


@pytest.mark.asyncio
async def test_trigger_missing_header_header_returns_401(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/pipeline/trigger",
            json={
                "manager_id": 1,
                "portfolio_id": 42,
                "company_id": 7,
            },
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_stream_unknown_note_returns_404(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/morning-notes/99999/stream",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
        )
    
    assert resp.status_code == 404
