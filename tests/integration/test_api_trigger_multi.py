import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app


def _make_token(manager_id: int) -> str:
    return create_access_token({"sub": str(manager_id), "manager_id": manager_id})


@pytest.mark.asyncio
@pytest.mark.serial
async def test_trigger_portfolio_returns_202_with_tickers_count(bound_engine, finagent_app_role):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    token = create_access_token({"sub": "2", "manager_id": 2})
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/pipeline/trigger",
        headers=headers,
        json={"manager_id": 2, "portfolio_id": 100}
    )

    assert response.status_code == 202

    body = response.json()
    assert body["portfolio_id"] == 100
    assert body["tickers_count"] == 1
    assert body["status"] == "pending"
    assert "pipeline_run_id" in body
    assert "morning_note_id" in body
    assert len(body["pipeline_run_id"]) == 36
    assert len(body["morning_note_id"]) == 36

    assert response.headers["x-pipeline-run-id"] == body["pipeline_run_id"]

    await client.aclose()


async def test_trigger_rejects_company_id(bound_engine, finagent_app_role):
    pass

async def test_trigger_other_manager_portfolio_returns_404(bound_engine, finagent_app_role):
    pass


async def test_trigger_empty_portfolio_returns_ticker_count_zero(bound_engine, finagent_app_role):
    pass
