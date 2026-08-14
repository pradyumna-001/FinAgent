from __future__ import annotations
import asyncio
from collections.abc import Generator
import os
import subprocess
from pathlib import Path

import asyncpg
import pytest
from docker.errors import DockerException
from testcontainers.community.postgres import PostgresContainer

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://placeholder@localhost:5432/placeholder",
)
os.environ.setdefault(
    "MIGRATION_DATABASE_URL",
    "postgresql://placeholder@localhost:5432/placeholder",
)


@pytest.fixture(scope="session")
def pg_container() -> Generator[PostgresContainer, None, None]:
    try:
        with PostgresContainer("pgvector/pgvector:pg16") as pg:
            yield pg
    except DockerException:
        pytest.skip(
            "Docker daemon not reachable. Start Docker Desktop or configure DOCKER_HOST."
        )


@pytest.fixture(scope="session")
def migrated_db_url(pg_container: PostgresContainer) -> Generator[str, None, None]:
    url = pg_container.get_connection_url(driver="asyncpg")
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        yield url
    finally:
        if original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_db_url


@pytest.fixture
def rls_role(migrated_db_url: str) -> Generator[str, None, None]:
    admin_url = migrated_db_url.replace("postgresql+asyncpg", "postgresql", 1)

    async def _admin() -> asyncpg.Connection:
        return await asyncpg.connect(admin_url)

    async def _setup() -> None:
        conn = await _admin()
        try:
            try:
                await conn.execute(
                    "CREATE ROLE rls_test NOSUPERUSER NOBYPASSRLS "
                    "LOGIN PASSWORD 'rls_test_pwd'"
                )
            except asyncpg.exceptions.DuplicateObjectError:
                pass
            await conn.execute("GRANT USAGE ON SCHEMA public TO rls_test")
            await conn.execute("GRANT SELECT ON morning_notes TO rls_test")
            await conn.execute(
                "INSERT INTO managers (id, name, email) VALUES "
                "(2, 'Alice', 'alice@example.com'), "
                "(3, 'Bob', 'bob@example.com') "
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
            await conn.execute("GRANT SELECT ON managers TO rls_test")
            await conn.execute("GRANT SELECT ON companies TO rls_test")
            await conn.execute("GRANT SELECT ON portfolios TO rls_test")
            await conn.execute("GRANT SELECT ON portfolio_holdings TO rls_test")
            await conn.execute("GRANT SELECT ON recommendations TO rls_test")
            await conn.execute("GRANT INSERT, UPDATE ON recommendations TO rls_test")
            await conn.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO rls_test")
        finally:
            await conn.close()

    async def _teardown() -> None:
        conn = await _admin()
        try:
            await conn.execute("DROP OWNED BY rls_test CASCADE")
            await conn.execute("DROP ROLE IF EXISTS rls_test")
        finally:
            await conn.close()

    asyncio.run(_setup())
    try:
        yield f"postgresql+asyncpg://rls_test:rls_test_pwd@{admin_url.split('@', 1)[1]}"
    finally:
        asyncio.run(_teardown())
        