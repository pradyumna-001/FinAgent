from __future__ import annotations
from typing import Any
import asyncpg


async def fetch_scalar(url: str, sql: str) -> Any:
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg", "postgresql", 1))
    try:
        return await conn.fetchval(sql)
    finally:
        await conn.close()
