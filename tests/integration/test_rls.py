from __future__ import annotations
from typing import Optional
import asyncpg
import pytest


async def _connect_as_role(url: str) -> asyncpg.Connection:
    return await asyncpg.connect(url.replace("postgresql+asyncpg", "postgresql", 1))


async def _set_manager_id(conn: asyncpg.Connection, value: Optional[str]) -> None:
    if value is None:
        await conn.execute("RESET app.manager_id")
    else:
        await conn.execute("SELECT set_config('app.manager_id', $1, false)", value)


async def _count_visible(conn: asyncpg.Connection) -> int:
    return await conn.fetchval("SELECT count(*) FROM morning_notes")


async def test_rls_filters_by_manager_id(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        assert await _count_visible(conn) == 2

        await _set_manager_id(conn, "3")
        assert await _count_visible(conn) == 1

        await _set_manager_id(conn, None)
        with pytest.raises(asyncpg.exceptions.InvalidTextRepresentationError):
            await _count_visible(conn)

        await _set_manager_id(conn, "banana")
        with pytest.raises(asyncpg.exceptions.InvalidTextRepresentationError):
            await _count_visible(conn)
    finally:
        await conn.close()


async def test_rls_managers_world_readable(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        assert await conn.fetchval("SELECT count(*) FROM managers") == 2
        await _set_manager_id(conn, "3")
        assert await conn.fetchval("SELECT count(*) FROM managers") == 2
    finally:
        await conn.close()


async def test_rls_companies_world_readable(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        assert await conn.fetchval("SELECT count(*) FROM companies") == 1
        await _set_manager_id(conn, "3")
        assert await conn.fetchval("SELECT count(*) FROM companies") == 1
    finally:
        await conn.close()


async def test_rls_portfolios_isolated(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        assert await conn.fetchval("SELECT count(*) FROM portfolios") == 1
        await _set_manager_id(conn, "3")
        assert await conn.fetchval("SELECT count(*) FROM portfolios") == 1
    finally:
        await conn.close()


async def test_rls_portfolio_holdings_isolated(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        assert await conn.fetchval("SELECT count(*) FROM portfolio_holdings") == 1
        await _set_manager_id(conn, "3")
        assert await conn.fetchval("SELECT count(*) FROM portfolio_holdings") == 1
    finally:
        await conn.close()


async def test_rls_recommendations_isolated(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        assert await conn.fetchval("SELECT count(*) FROM recommendations") == 1
        await _set_manager_id(conn, "3")
        assert await conn.fetchval("SELECT count(*) FROM recommendations") == 1
    finally:
        await conn.close()


async def test_rls_recommendations_insert_cross_tenant_rejected(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO recommendations (morning_note_id, action, confidence, justification) "
                "VALUES (3, 'buy', 0.9, 'steal')"
            )
    finally:
        await conn.close()
