import pytest
from httpx import ASGITransport, AsyncClient

from app.core.context import current_morning_note_id, current_pipeline_run_id
from app.main import app


@pytest.mark.asyncio
async def test_correlation_headers_set_contextvars_during_request() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get(
            "/morning-notes",
            headers={
                "X-Pipeline-Run-Id": "pipe-123",
                "X-Morning-Note-Id": "note-456",
            },
        )
    assert current_pipeline_run_id.get() is None
    assert current_morning_note_id.get() is None


@pytest.mark.asyncio
async def test_correlation_no_headers_leaves_contextvars_none() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/morning-notes")
    assert current_pipeline_run_id.get() is None
    assert current_morning_note_id.get() is None
