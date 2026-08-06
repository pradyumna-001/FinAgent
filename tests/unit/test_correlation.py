import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.core.context import current_morning_note_id, current_pipeline_run_id
from app.middleware.correlation import CorrelationMiddleware


def _build_app() -> Starlette:
    async def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    return Starlette(
        routes=[Route("/", homepage)],
        middleware=[Middleware(CorrelationMiddleware)],
    )


@pytest.mark.asyncio
async def test_correlation_headers_set_contextvars_during_request() -> None:
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get(
            "/",
            headers={
                "X-Pipeline-Run-Id": "pipe-123",
                "X-Morning-Note-Id": "note-456",
            },
        )
    assert current_pipeline_run_id.get() is None
    assert current_morning_note_id.get() is None


@pytest.mark.asyncio
async def test_correlation_no_headers_leaves_contextvars_none() -> None:
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/")
    assert current_pipeline_run_id.get() is None
    assert current_morning_note_id.get() is None