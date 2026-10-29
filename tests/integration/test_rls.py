from __future__ import annotations

import json
import sys
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
                   'manager_decision', COALESCE(r.manager_decision, 'pending'),
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


@pytest.mark.serial
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


@pytest.mark.serial
async def test_rls_managers_world_readable(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        # Fixture inserts managers 2 and 3; RLS policy is world-readable so all are visible
        # At least 2 should be visible (our test data)
        assert await conn.fetchval("SELECT count(*) FROM managers") >= 2
        await _set_manager_id(conn, "3")
        assert await conn.fetchval("SELECT count(*) FROM managers") >= 2
    finally:
        await conn.close()


@pytest.mark.serial
async def test_rls_companies_world_readable(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        assert await conn.fetchval("SELECT count(*) FROM companies") == 1
        await _set_manager_id(conn, "3")
        assert await conn.fetchval("SELECT count(*) FROM companies") == 1
    finally:
        await conn.close()


@pytest.mark.serial
async def test_rls_portfolios_isolated(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        assert await conn.fetchval("SELECT count(*) FROM portfolios") == 1
        await _set_manager_id(conn, "3")
        assert await conn.fetchval("SELECT count(*) FROM portfolios") == 1
    finally:
        await conn.close()


@pytest.mark.serial
async def test_rls_portfolio_holdings_isolated(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        assert await conn.fetchval("SELECT count(*) FROM portfolio_holdings") == 1
        await _set_manager_id(conn, "3")
        assert await conn.fetchval("SELECT count(*) FROM portfolio_holdings") == 1
    finally:
        await conn.close()


@pytest.mark.serial
async def test_rls_recommendations_isolated(finagent_app_role: str) -> None:
    conn = await _connect_as_role(finagent_app_role)
    try:
        await _set_manager_id(conn, "2")
        assert await conn.fetchval("SELECT count(*) FROM recommendations") == 1
        await _set_manager_id(conn, "3")
        assert await conn.fetchval("SELECT count(*) FROM recommendations") == 1
    finally:
        await conn.close()


@pytest.mark.serial
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


@pytest.mark.serial
async def test_rls_recommendations_jsonb_isolated(
    finagent_app_role: str, admin_db_url: str
) -> None:
    """RLS filters MorningNote.recommendations JSONB by manager_id.

    Verifies the new JSONB column (added in Phase 1-2 of #123) is properly
    isolated by RLS and that JSONB structure is intact (per-ticker keys present).
    """
    # Run backfill as superuser (no RLS) to populate recommendations for fixture data
    admin_conn = await asyncpg.connect(admin_db_url)
    try:
        async with admin_conn.transaction():
            notes_before = await admin_conn.fetch(
                "SELECT id, note_text, company_id, recommendations FROM morning_notes ORDER BY note_text"
            )
            sys.stderr.write(f"DEBUG: morning_notes before: {[(n['note_text'], n['company_id'], n['recommendations']) for n in notes_before]}\n")

            recs_before = await admin_conn.fetch(
                "SELECT r.morning_note_id, r.action, r.confidence, mn.company_id, c.ticker "
                "FROM recommendations r "
                "JOIN morning_notes mn ON mn.id = r.morning_note_id "
                "JOIN companies c ON c.id = mn.company_id"
            )
            sys.stderr.write(f"DEBUG: recommendations join: {[(r['morning_note_id'], r['action'], r['ticker']) for r in recs_before]}\n")

            result = await admin_conn.execute(BACKFILL_SQL)
            sys.stderr.write(f"DEBUG: backfill result: {result}\n")

            notes_after = await admin_conn.fetch(
                "SELECT id, note_text, company_id, recommendations FROM morning_notes ORDER BY note_text"
            )
            sys.stderr.write(f"DEBUG: morning_notes after: {[(n['note_text'], n['company_id'], n['recommendations']) for n in notes_after]}\n")
    finally:
        await admin_conn.close()

    conn = await _connect_as_role(finagent_app_role)
    try:
        # Manager 2 has 2 morning notes (note-a1 has recommendation, note-a2 does not)
        await _set_manager_id(conn, "2")
        rows = await conn.fetch(
            "SELECT note_text, recommendations FROM morning_notes ORDER BY note_text"
        )
        assert len(rows) == 2, f"Manager 2 should see 2 notes, got {len(rows)}"
        # note-a1 has recommendation -> backfilled with AAPL
        rec_a1 = rows[0]["recommendations"]
        rec_dict_a1 = json.loads(rec_a1) if isinstance(rec_a1, str) else rec_a1
        assert "AAPL" in rec_dict_a1, f"Expected AAPL key in note-a1: {rec_dict_a1}"
        aapl_a1 = rec_dict_a1["AAPL"]
        assert aapl_a1["action"] == "buy"
        assert aapl_a1["confidence"] == 0.8
        # note-a2 has NO recommendation -> stays as empty {}
        rec_a2 = rows[1]["recommendations"]
        rec_dict_a2 = json.loads(rec_a2) if isinstance(rec_a2, str) else rec_a2
        assert rec_dict_a2 == {}, f"Expected empty for note-a2: {rec_dict_a2}"

        # Manager 3 has 1 morning note (note-b1) with recommendation
        await _set_manager_id(conn, "3")
        rows = await conn.fetch(
            "SELECT note_text, recommendations FROM morning_notes ORDER BY note_text"
        )
        assert len(rows) == 1, f"Manager 3 should see 1 note, got {len(rows)}"
        rec = rows[0]["recommendations"]
        rec_dict = json.loads(rec) if isinstance(rec, str) else rec
        assert "AAPL" in rec_dict, f"Expected AAPL key in recommendations: {rec_dict}"
        aapl = rec_dict["AAPL"]
        assert aapl["action"] == "hold"
        assert aapl["confidence"] == 0.6

        # No manager_id set -> should raise (RLS blocks all)
        await _set_manager_id(conn, None)
        with pytest.raises(asyncpg.exceptions.InvalidTextRepresentationError):
            await conn.fetchval("SELECT recommendations FROM morning_notes LIMIT 1")
    finally:
        await conn.close()
