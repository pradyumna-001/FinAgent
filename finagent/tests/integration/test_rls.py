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


async def test_rls_filters_by_manager_id(rls_role: str) -> None:
    conn = await _connect_as_role(rls_role)
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
