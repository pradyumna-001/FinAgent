import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.security import create_access_token


def _make_token(manager_id: int) -> str:
    return create_access_token({"sub": str(manager_id), "manager_id": manager_id})


@pytest.mark.asyncio
async def test_list_morning_notes_missing_header_returns_401() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_morning_notes_with_header_returns_list(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
    print(resp.json())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_read_morning_notes_with_header_returns_all_fields(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
        notes = resp.json()
        note_id = notes[0]["id"]

        resp = await client.get(
            f"/morning-notes/{note_id}",
            headers={"Authorization": f"Bearer {_make_token(2)}"}
        )

        assert resp.status_code == 200
        data = resp.json()

        assert data["id"] == note_id
        assert isinstance(data["id"], int)
        assert isinstance(data["generated_at"], str)
        assert isinstance(data["note_text"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["confidence_scores"], dict)
        assert isinstance(data["data_freshness"], dict)
        assert isinstance(data["flags"], (list, dict))
        assert data["pipeline_run_id"] is None or isinstance(data["pipeline_run_id"], str)
        
        rec = data["recommendation"]
        assert rec is None or isinstance(rec, dict)
        if rec:
            assert isinstance(rec["action"], str)
            assert isinstance(rec["confidence"], float)
            assert isinstance(rec["justification"], str)
            assert isinstance(rec["created_at"], str)
            assert rec["confirmed_at"] is None or isinstance(rec["confirmed_at"], str)
        
        assert isinstance(data["manager_name"], str)
        assert isinstance(data["company_ticker"], str)
        assert isinstance(data["company_name"], str)


@pytest.mark.asyncio
async def test_read_morning_note_missing_header_returns_401(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
        notes = resp.json()
        note_id = notes[0]["id"]

        resp = await client.get(f"/morning-notes/{note_id}")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_read_morning_notes_rls_isolation_returns_404(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
        notes = resp.json()
        note_id = notes[0]["id"]

        resp = await client.get(
            f"/morning-notes/{note_id}",
            headers={"Authorization": f"Bearer {_make_token(3)}"}
        )

        assert resp.status_code == 404
        assert resp.json() == {"detail": "Morning note not found"}


@pytest.mark.asyncio
async def test_read_morning_notes_nonexistent_note_returns_404(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        note_id = 999

        resp = await client.get(
            f"/morning-notes/{note_id}",
            headers={"Authorization": f"Bearer {_make_token(2)}"}
        )

        assert resp.status_code == 404
        assert resp.json() == {"detail": "Morning note not found"}
