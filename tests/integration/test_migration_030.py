"""Tests for ADR-030 migration: Multi-Ticker Morning Notes schema changes (Phases 1-2)."""

import json

import asyncpg
import pytest


async def _connect(url: str) -> asyncpg.Connection:
    return await asyncpg.connect(url.replace("postgresql+asyncpg", "postgresql", 1))


async def _set_manager_id(conn: asyncpg.Connection, value: str) -> None:
    await conn.execute("SELECT set_config('app.manager_id', $1, false)", value)


async def _fetch_scalar(conn: asyncpg.Connection, sql: str, *args) -> any:
    return await conn.fetchval(sql, *args)


async def _execute(conn: asyncpg.Connection, sql: str, *args) -> str:
    return await conn.execute(sql, *args)


BACKFILL_SQL = """
UPDATE morning_notes mn
SET recommendations = sub.recs
FROM (
    SELECT r.morning_note_id,
           jsonb_build_object(
               c.ticker, jsonb_build_object(
                   'action', r.action,
                   'confidence', r.confidence,
                   'justification', r.justification,
                   'manager_decision', r.manager_decision,
                   'decided_at', r.decided_at,
                   'decision_channel', r.decision_channel
               )
           ) as recs
    FROM recommendations r
    JOIN morning_notes mn2 ON mn2.id = r.morning_note_id
    JOIN companies c ON c.id = mn2.company_id
    WHERE mn2.company_id IS NOT NULL
) sub
WHERE sub.morning_note_id = mn.id
  AND mn.company_id IS NOT NULL;
"""


@pytest.mark.asyncio
@pytest.mark.serial
async def test_recommendations_column_exists(migrated_db_url: str) -> None:
    """Phase 1: recommendations JSONB column added with correct type and default."""
    conn = await _connect(migrated_db_url)
    try:
        col_type = await _fetch_scalar(
            conn,
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
            "WHERE c.relname='morning_notes' AND a.attname='recommendations'",
        )
        assert col_type == "jsonb"

        col_default = await _fetch_scalar(
            conn,
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name='morning_notes' AND column_name='recommendations'",
        )
        assert col_default == "'{}'::jsonb"

        is_nullable = await _fetch_scalar(
            conn,
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name='morning_notes' AND column_name='recommendations'",
        )
        assert is_nullable == "NO"
    finally:
        await conn.close()


@pytest.mark.asyncio
@pytest.mark.serial
async def test_backfill_populates_recommendations_jsonb_manager_2(
    finagent_app_role: str
) -> None:
    """Phase 2: Backfill correctly builds JSONB for manager 2's notes."""
    conn = await _connect(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")

        # Run backfill (sees only manager 2's recommendations due to RLS)
        await _execute(conn, BACKFILL_SQL)

        # note-a1 has recommendation -> backfilled
        rec = await _fetch_scalar(
            conn,
            "SELECT recommendations FROM morning_notes WHERE note_text = 'note-a1'",
        )
        rec_dict = json.loads(rec) if isinstance(rec, str) else rec
        assert "AAPL" in rec_dict, f"Expected AAPL in rec_dict: {rec_dict}"

        aapl_rec = rec_dict["AAPL"]
        assert aapl_rec["action"] == "buy"
        assert aapl_rec["confidence"] == 0.8
        assert aapl_rec["justification"] == "Strong fundamentals"
        assert aapl_rec["manager_decision"] == "pending"
        assert aapl_rec["decided_at"] is None
        assert aapl_rec["decision_channel"] is None

        # note-a2 has NO recommendation -> stays as default '{}'
        rec = await _fetch_scalar(
            conn,
            "SELECT recommendations FROM morning_notes WHERE note_text = 'note-a2'",
        )
        rec_dict = json.loads(rec) if isinstance(rec, str) else rec
        assert rec_dict == {}
    finally:
        await conn.close()


@pytest.mark.asyncio
@pytest.mark.serial
async def test_backfill_populates_recommendations_jsonb_manager_3(
    finagent_app_role: str
) -> None:
    """Phase 2: Backfill correctly builds JSONB for manager 3's notes."""
    conn = await _connect(finagent_app_role)
    try:
        await _set_manager_id(conn, "3")

        # Run backfill (sees only manager 3's recommendations due to RLS)
        await _execute(conn, BACKFILL_SQL)

        # note-b1 has recommendation -> backfilled
        rec = await _fetch_scalar(
            conn,
            "SELECT recommendations FROM morning_notes WHERE note_text = 'note-b1'",
        )
        rec_dict = json.loads(rec) if isinstance(rec, str) else rec
        assert "AAPL" in rec_dict, f"Expected AAPL in rec_dict: {rec_dict}"

        aapl_rec = rec_dict["AAPL"]
        assert aapl_rec["action"] == "hold"
        assert aapl_rec["confidence"] == 0.6
        assert aapl_rec["justification"] == "Mixed signals"
    finally:
        await conn.close()


@pytest.mark.asyncio
@pytest.mark.serial
async def test_old_single_ticker_notes_retain_company_id(
    finagent_app_role: str
) -> None:
    """Phase 1-2: Old notes retain company_id; cutover (Phase 4) drops it later."""
    conn = await _connect(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")

        company_id = await _fetch_scalar(
            conn,
            "SELECT company_id FROM morning_notes WHERE note_text = 'note-a1'",
        )
        assert company_id is not None
        assert company_id == 10  # AAPL
    finally:
        await conn.close()


@pytest.mark.asyncio
@pytest.mark.serial
async def test_company_id_still_not_null(migrated_db_url: str) -> None:
    """company_id is still NOT NULL; Phase 4 (cutover) will drop the constraint."""
    conn = await _connect(migrated_db_url)
    try:
        is_nullable = await _fetch_scalar(
            conn,
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name='morning_notes' AND column_name='company_id'",
        )
        assert is_nullable == "NO"
    finally:
        await conn.close()