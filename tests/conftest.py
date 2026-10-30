from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Iterator

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Try to import testcontainers; skip if not available
try:
    from docker.errors import DockerException
    from testcontainers.community.postgres import PostgresContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False
    DockerException = Exception

from app.utils.security import hash_password

# Windows: psycopg async requires SelectorEventLoop, not ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# Default fallback URLs (used when no container)
DEFAULT_DB_URL_ASYNC = "postgresql+asyncpg://finagent:password@localhost:5434/finagent"
DEFAULT_DB_URL_SYNC = "postgresql+psycopg://finagent:password@localhost:5434/finagent"
DEFAULT_DB_URL_ADMIN = "postgresql://finagent:password@localhost:5434/finagent"

os.environ.setdefault("DATABASE_URL", DEFAULT_DB_URL_ASYNC)
os.environ.setdefault("MIGRATION_DATABASE_URL", DEFAULT_DB_URL_SYNC)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "TEST_SECRET_KEY_REPLACE_IN_PRODUCTION")
os.environ.setdefault("TAVILY_API_KEY", "tvly-TEST_KEY_REPLACE_IN_PRODUCTION")
os.environ.setdefault("NVIDIA_API_KEY", "nvapi-TEST_KEY_REPLACE_IN_PRODUCTION")
os.environ.setdefault("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
os.environ.setdefault("NVIDIA_MODEL", "openai/gpt-oss-20b")
os.environ.setdefault("NVIDIA_FALLBACK_MODEL", "openai/gpt-oss-20b")
os.environ.setdefault("NVIDIA_NEMOTRON_MODEL", "nvidia/nemotron-3-ultra")
os.environ.setdefault("LANGCHAIN_API_KEY", "")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

import app.db.session as db_session


# Detect if we're in CI (GitHub Actions) or have Docker available
IN_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
DOCKER_AVAILABLE = False

if TESTCONTAINERS_AVAILABLE:
    try:
        import docker
        client = docker.from_env()
        client.ping()
        DOCKER_AVAILABLE = True
    except Exception:
        DOCKER_AVAILABLE = False


# Use testcontainers in CI (Linux), existing PostgreSQL locally (Windows)
USE_TESTCONTAINERS = IN_CI and DOCKER_AVAILABLE


@pytest.fixture(scope="session")
def pg_container() -> Generator["PostgresContainer", None, None]:
    """PostgreSQL container for CI. Uses existing PG on Windows/local."""
    if not USE_TESTCONTAINERS:
        pytest.skip("Using existing PostgreSQL; testcontainers not needed")
    
    try:
        with PostgresContainer("pgvector/pgvector:pg16") as pg:
            yield pg
    except DockerException:
        pytest.skip("Docker daemon not reachable. Start Docker Desktop or configure DOCKER_HOST.")


@pytest.fixture(scope="session")
def migrated_db_url(pg_container) -> Generator[str, None, None]:
    """Run migrations against test database and yield connection URL."""
    if USE_TESTCONTAINERS:
        url = pg_container.get_connection_url(driver="asyncpg")
        admin_url = pg_container.get_connection_url(driver="psycopg")
    else:
        url = DEFAULT_DB_URL_ASYNC
        admin_url = DEFAULT_DB_URL_SYNC
    
    original_db_url = os.environ.get("DATABASE_URL")
    original_migration_url = os.environ.get("MIGRATION_DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    os.environ["MIGRATION_DATABASE_URL"] = admin_url
    try:
        subprocess.run(
            ["alembic", "upgrade", "heads"],
            check=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        yield url
    finally:
        if original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_db_url
        if original_migration_url is None:
            os.environ.pop("MIGRATION_DATABASE_URL", None)
        else:
            os.environ["MIGRATION_DATABASE_URL"] = original_migration_url


@pytest.fixture(scope="session")
def admin_db_url(pg_container) -> str:
    """Admin (superuser) connection URL for test setup/teardown."""
    if USE_TESTCONTAINERS:
        url = pg_container.get_connection_url(driver="psycopg")
    else:
        url = DEFAULT_DB_URL_ADMIN
    # asyncpg requires 'postgresql' scheme, not 'postgresql+psycopg'
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(scope="session")
def finagent_app_role(migrated_db_url: str, admin_db_url: str) -> Generator[str, None, None]:

    async def _admin() -> asyncpg.Connection:
        return await asyncpg.connect(admin_db_url)

    async def _setup() -> None:
        conn = await _admin()
        try:
            await conn.execute(
                "ALTER ROLE finagent_app WITH PASSWORD 'finagent_app_pwd'"
            )
            alice_hash = hash_password("alice123")
            bob_hash = hash_password("bob123")
            await conn.execute(
                "INSERT INTO managers (id, name, email, password_hash) VALUES "
                f"(2, 'Alice', 'alice@example.com', '{alice_hash}'), "
                f"(3, 'Bob', 'bob@example.com', '{bob_hash}') "
                "ON CONFLICT (id) DO NOTHING"
            )
            await conn.execute(
                "INSERT INTO companies (id, ticker, name) VALUES "
                "(10, 'AAPL', 'Apple Inc') "
                "ON CONFLICT (id) DO NOTHING"
            )
            await conn.execute(
                "INSERT INTO portfolios (id, manager_id, name) VALUES "
                "(100, 2, 'Alice growth'), (200, 3, 'Bob value') "
                "ON CONFLICT (id) DO NOTHING"
            )
            await conn.execute(
                "INSERT INTO morning_notes "
                "(portfolio_id, manager_id, company_id, note_text) "
                "SELECT * FROM (VALUES "
                "(100, 2, 10, 'note-a1'), (100, 2, 10, 'note-a2'), "
                "(200, 3, 10, 'note-b1') "
                ") AS v(portfolio_id, manager_id, company_id, note_text) "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM morning_notes mn "
                "WHERE mn.portfolio_id = v.portfolio_id "
                "AND mn.note_text = v.note_text"
                ")"
            )
            await conn.execute(
                "INSERT INTO portfolio_holdings (portfolio_id, company_id, weight) "
                "SELECT * FROM (VALUES "
                "(100, 10, 0.5), (200, 10, 1.0) "
                ") AS v(portfolio_id, company_id, weight) "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM portfolio_holdings ph "
                "WHERE ph.portfolio_id = v.portfolio_id "
                "AND ph.company_id = v.company_id"
                ")"
            )
            await conn.execute(
                "INSERT INTO recommendations "
                "(morning_note_id, action, confidence, justification) "
                "SELECT id, 'buy', 0.8, 'Strong fundamentals' "
                "FROM morning_notes WHERE note_text = 'note-a1' "
                "AND NOT EXISTS (SELECT 1 FROM recommendations r WHERE r.morning_note_id = morning_notes.id)"
                "UNION ALL "
                "SELECT id, 'hold', 0.6, 'Mixed signals' "
                "FROM morning_notes WHERE note_text = 'note-b1' "
                "AND NOT EXISTS (SELECT 1 FROM recommendations r WHERE r.morning_note_id = morning_notes.id)"
            )
            await conn.execute(
                "INSERT INTO feedbacks "
                "(morning_note_id, manager_id, action, justification, comment) "
                "SELECT id, 2, 'buy', 'Strong fundamentals', 'really cool' "
                "FROM morning_notes WHERE note_text = 'note-a1' "
                "AND NOT EXISTS (SELECT 1 FROM feedbacks f WHERE f.morning_note_id = morning_notes.id)"
            )
        finally:
            await conn.close()

    async def _teardown() -> None:
        conn = await _admin()
        try:
            await conn.execute("DROP OWNED BY finagent_app CASCADE")
            await conn.execute("DROP ROLE IF EXISTS finagent_app")
        finally:
            await conn.close()

    asyncio.run(_setup())
    try:
        if USE_TESTCONTAINERS:
            # Extract host/port from admin_db_url
            host_port = admin_db_url.split('@', 1)[1]
            yield f"postgresql+asyncpg://finagent_app:finagent_app_pwd@{host_port}"
        else:
            yield f"postgresql+asyncpg://finagent_app:finagent_app_pwd@localhost:5434/finagent"
    finally:
        asyncio.run(_teardown())


@pytest.fixture
def bound_engine(migrated_db_url: str) -> Iterator[None]:
    engine = create_async_engine(migrated_db_url, echo=False)
    db_session.engine = engine
    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    yield
    engine.sync_engine.dispose()