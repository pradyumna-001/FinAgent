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

from app.utils.security import hash_password

# Windows: psycopg async requires SelectorEventLoop, not ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# Use existing PostgreSQL on port 5434 (started manually via Docker)
# This avoids testcontainer connection reset issues on Windows
EXISTING_PG_URL_ASYNC = "postgresql+asyncpg://finagent:password@localhost:5434/finagent"
EXISTING_PG_URL_SYNC = "postgresql+psycopg://finagent:password@localhost:5434/finagent"
EXISTING_PG_URL_ADMIN = "postgresql://finagent:password@localhost:5434/finagent"

os.environ.setdefault("DATABASE_URL", EXISTING_PG_URL_ASYNC)
os.environ.setdefault("MIGRATION_DATABASE_URL", EXISTING_PG_URL_SYNC)
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


@pytest.fixture(scope="session")
def existing_pg_url() -> str:
    """Connection URL for existing PostgreSQL on port 5434."""
    return EXISTING_PG_URL_ASYNC


@pytest.fixture(scope="session")
def migrated_db_url(existing_pg_url: str) -> Generator[str, None, None]:
    """Run migrations against existing PostgreSQL and yield connection URL."""
    original_db_url = os.environ.get("DATABASE_URL")
    original_migration_url = os.environ.get("MIGRATION_DATABASE_URL")
    os.environ["DATABASE_URL"] = existing_pg_url
    os.environ["MIGRATION_DATABASE_URL"] = EXISTING_PG_URL_SYNC
    try:
        subprocess.run(
            ["alembic", "upgrade", "heads"],
            check=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        yield existing_pg_url
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
def admin_db_url() -> str:
    """Admin (superuser) connection URL for test setup/teardown."""
    return EXISTING_PG_URL_ADMIN


@pytest.fixture(scope="session")
def finagent_app_role(migrated_db_url: str, admin_db_url: str) -> Generator[str, None, None]:

    async def _admin() -> asyncpg.Connection:
        return await asyncpg.connect(admin_db_url)

    async def _setup() -> None:
        conn = await _admin()
        try:
            # Set password for finagent_app role (migration creates it without password)
            await conn.execute(
                "ALTER ROLE finagent_app WITH PASSWORD 'finagent_app_pwd'"
            )
            # Insert test data
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