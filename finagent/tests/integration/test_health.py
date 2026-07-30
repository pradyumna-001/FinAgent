import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from app.main import app


@pytest.mark.asyncio
async def test_health_returns_503_when_db_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _RaisingConn:
        async def __aenter__(self): raise OperationalError("stmt", {}, Exception("down"))
        async def __aexit__(self, *a): return False


    class _StubEngine:
        def begin(self):
            return _RaisingConn()


    monkeypatch.setattr("app.main.engine", _StubEngine())
    transport = ASGITransport(app=app)


    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")


    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "db": "unreachable"}
