from httpx import ASGITransport, AsyncClient
import pytest

from app.core.security import create_access_token
from app.main import app


def _make_token(manager_id: int) -> str:
    return create_access_token({"sub": str(manager_id), "manager_id": manager_id})


async def test_create_feedback_success_201(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
        notes = resp.json()
        note_id = notes[0]["id"]

        resp = await client.post(
            f"/morning-notes/{note_id}/feedback",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
            json={
                "action": "buy",
                "justification": "Strong fundamentals",
                "comment": "Long term hold"
            }
        )

        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert isinstance(data["id"], int)
        assert "created_at" in data


@pytest.mark.asyncio
async def test_create_feedback_missing_header_returns_401() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/morning-notes/1/feedback",
            json={
                "action": "buy",
                "justification": "Strong fundamentals"
            }
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_feedback_invalid_manager_id_returns_401(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
        notes = resp.json()
        note_id = notes[0]["id"]

        resp = await client.post(
            f"/morning-notes/{note_id}/feedback",
            headers={"Authorization": f"Bearer {_make_token(-1)}"},
            json={
                "action": "buy",
                "justification": "Strong fundamentals",
                "comment": "Long term hold"
            }
        )

        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_feedback_valid_manager_non_existent_note_id_returns_404(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        note_id = 999

        resp = await client.post(
            f"/morning-notes/{note_id}/feedback",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
            json={
                "action": "buy",
                "justification": "Strong fundamentals",
                "comment": "Long term hold"
            }
        )

        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_manager_a_posts_on_manager_b_note_returns_404(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
        notes = resp.json()
        note_id = notes[0]["id"]

        resp = await client.post(
            f"/morning-notes/{note_id}/feedback",
            headers={"Authorization": f"Bearer {_make_token(3)}"},
            json={
                "action": "buy",
                "justification": "Strong fundamentals",
                "comment": "Long term hold"
            }
        )
        
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_create_feedback_missing_fields_returns_422(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
        notes = resp.json()
        note_id = notes[0]["id"]

        resp = await client.post(
            f"/morning-notes/{note_id}/feedback",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
            json={
                "justification": "Strong fundamentals",
            }
        )

        assert resp.status_code == 422
        assert resp.json()["code"] == "VALIDATION_ERROR"
        assert "action" in resp.json()["details"]


@pytest.mark.asyncio
async def test_create_feedback_invalid_action_returns_422(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
        notes = resp.json()
        note_id = notes[0]["id"]

        resp = await client.post(
            f"/morning-notes/{note_id}/feedback",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
            json={
                "action": "stand still",
                "justification": "Strong fundamentals",
            }
        )

        assert resp.status_code == 422
        assert resp.json()["code"] == "VALIDATION_ERROR"
        assert "action" in resp.json()["details"]


@pytest.mark.asyncio
async def test_create_feedback_short_justification_422(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
        notes = resp.json()
        note_id = notes[0]["id"]

        resp = await client.post(
            f"/morning-notes/{note_id}/feedback",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
            json={
                "action": "buy",
                "justification": "short",
            }
        )

        assert resp.status_code == 422
        assert resp.json()["code"] == "VALIDATION_ERROR"
        assert "justification" in resp.json()["details"]


@pytest.mark.asyncio
async def test_create_duplicated_feedback_returns_409(bound_engine: None, finagent_app_role: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes", headers={"Authorization": f"Bearer {_make_token(2)}"})
        notes = resp.json()
        note_id = [n["id"] for n in notes if n["note_text"] == "note-a1"][0]

        resp = await client.post(
            f"/morning-notes/{note_id}/feedback",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
            json={
                "action": "buy",
                "justification": "Strong fundamentals",
                "comment": "really cool"
            }
        )

        assert resp.status_code == 409
        assert resp.json()["code"] == "CONFLICT"
