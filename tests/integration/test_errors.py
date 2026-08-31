from datetime import datetime

from httpx import ASGITransport, AsyncClient
import pytest

from fastapi import FastAPI, Request

from app.api.errors import ApiError, ErrorCodes, json_response_from_api_error
from app.core.security import create_access_token
from app.main import app


def _make_token(manager_id: int) -> str:
    return create_access_token({"sub": str(manager_id), "manager_id": manager_id})


def _assert_shape(body: dict) -> None:
    assert "code" in body
    assert "message" in body
    assert "path" in body
    assert "timestamp" in body
    dt = datetime.fromisoformat(body["timestamp"])
    offset = dt.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


async def _first_note_id(client: AsyncClient, manager_id: int) -> int:
    resp = await client.get(
        "/morning-notes", headers={"Authorization": f"Bearer {_make_token(manager_id)}"}
    )
    assert resp.status_code == 200
    notes = resp.json()
    assert notes
    return notes[0]["id"]


@pytest.mark.asyncio
async def test_missing_header_returns_401_and_shape(
    bound_engine: None, finagent_app_role: None
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/morning-notes/1/feedback")
    assert resp.status_code == 401
    _assert_shape(resp.json())


@pytest.mark.asyncio
async def test_validation_error_details_grouped_by_field(
    bound_engine: None, finagent_app_role: None
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        note_id = await _first_note_id(client, 2)
        resp = await client.post(
            f"/morning-notes/{note_id}/feedback",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
            json={"justification": "Strong fundamentals"},
        )

    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "action" in body["details"]
    assert isinstance(body["details"]["action"], list)
    _assert_shape(body)


@pytest.mark.asyncio
async def test_registry_miss_returns_no_active_run(
    bound_engine: None, finagent_app_role: None
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        note_id = await _first_note_id(client, 2)
        resp = await client.get(
            f"/morning-notes/{note_id}/stream",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
        )

    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NO_ACTIVE_RUN"
    _assert_shape(body)


@pytest.mark.asyncio
async def test_nonexistent_note_returns_not_found_and_shape(
    bound_engine: None, finagent_app_role: None
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/morning-notes/999999999/stream",
            headers={"Authorization": f"Bearer {_make_token(2)}"},
        )

    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    _assert_shape(body)


async def _error_handler(request, exc):
    api_error = ApiError(
        status_code=500,
        code=ErrorCodes.INTERNAL_ERROR,
        message="Internal server error",
    )
    return json_response_from_api_error(api_error, request)


async def _boom(request: Request):
    raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500_no_traceback(
    bound_engine: None, finagent_app_role: None
) -> None:
    isolated = FastAPI()
    isolated.add_exception_handler(Exception, _error_handler)
    isolated.add_api_route("/_test/boom", _boom, methods=["GET"])

    transport = ASGITransport(app=isolated, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/_test/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert "Traceback" not in resp.text
    assert "Stack" not in resp.text
    _assert_shape(body)