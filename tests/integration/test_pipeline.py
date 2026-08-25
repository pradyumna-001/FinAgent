import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_trigger_returns_202_with_ids() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/pipeline/trigger",
            headers={"manager-id": "1"},
            json={
                "manager_id": 1,
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
async def test_trigger_missing_header_header_returns_400() -> None:
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
    assert resp.status_code == 400


@pytest.mark.skip(reason="Old stub test - replaced by test_sse.py integration tests")
@pytest.mark.asyncio
async def test_stream_known_note_returns_one_event() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://") as client:
        trigger = await client.post(
            "/pipeline/trigger",
            headers={"manager-id": "1"},
            json={"manager_id": 1, "portfolio_id": 42, "company_id": 7},
        )
        note_id = trigger.json()["morning_note_id"]

        async with client.stream(
            "GET", f"/morning-notes/{note_id}/stream"
        ) as stream_resp:
            assert stream_resp.status_code == 200
            lines = []
            async for line in stream_resp.aiter_lines():
                lines.append(line)

        data_lines = [line for line in lines if line.startswith("data:")]
        assert len(data_lines) == 1
        assert note_id in data_lines[0]


@pytest.mark.asyncio
async def test_stream_unknown_note_returns_404() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/morning-notes/00000000-0000-0000-0000-000000000000/stream")

    assert resp.status_code == 404
