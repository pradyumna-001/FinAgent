from httpx import ASGITransport, AsyncClient
import pytest

from app.main import app
from app.core.security import create_access_token


def _make_token(manager_id: int, email: str = "test@example.com") -> str:
    return create_access_token({"manager_id": manager_id, "sub": email})


@pytest.mark.asyncio
async def test_login_valid_credentials_returns_token(
    bound_engine: None, 
    finagent_app_role: None
) -> None:
    """Valid email + password returns access token."""
    # 1. Need manager with password hash in DB (add to fixture or setup here)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/login", json={
            "email": "alice@example.com",
            "password": "alice123"
        })

        assert resp.status_code == 200
        assert "access_token" in resp.json()
        assert resp.json()["token_type"] == "bearer"
        assert resp.json()["manager"]["email"] == "alice@example.com"    


@pytest.mark.asyncio
async def test_login_invalid_password_returns_401(
    bound_engine: None, 
    finagent_app_role: None
) -> None:
    """Wrong password returns 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/login", json={
            "email": "alice@example.com",
            "password": "wrong-password"
        })

        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email_returns_401(
    bound_engine: None, 
    finagent_app_role: None
) -> None:
    """Non-existent email returns 401 (same as wrong password)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/login", json={
            "email": "prady@example.com",
            "password": "wrong-password"
        })

        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_missing_fields_returns_422(
    bound_engine: None, 
    finagent_app_role: None
) -> None:
    """Missing email or password returns 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/login", json={
            "email": "alice@example.com",
            "password_hash": "alice123"
        })

        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_me_valid_token_returns_manager(
    bound_engine: None, 
    finagent_app_role: None
) -> None:
    """Valid JWT returns manager info."""
    token = _make_token(2, "alice@example.com")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 2
        assert data["name"] == "Alice"
        assert data["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_me_no_token_returns_401(
    bound_engine: None, 
    finagent_app_role: None
) -> None:
    """Missing Authorization header returns 401."""
    token = ""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        print(resp.json())
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_invalid_token_returns_401(
    bound_engine: None, 
    finagent_app_role: None
) -> None:
    """Invalid/malformed token returns 401."""
    token = _make_token(2, "alice@example.com")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}.not.valid.token"})
        assert resp.status_code == 401


# --- Protected routes with JWT (after routes updated) ---

# @pytest.mark.asyncio
# async def test_list_morning_notes_jwt_works(
#     bound_engine: None, 
#     finagent_app_role: None
# ) -> None:
#     """JWT auth works for morning-notes list."""
#     pass