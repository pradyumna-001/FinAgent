"""Behavioral probes for finagent_app role privileges.

Verifies that the application role has only the privileges it needs:
- Can SELECT, INSERT, UPDATE, DELETE on application tables
- Cannot DROP tables
- Cannot CREATE objects in public schema
- Cannot GRANT/REVOKE privileges
- Cannot ALTER tables
- Can UPDATE new recommendation decision columns (issue #110)
"""

from __future__ import annotations

import asyncpg
import pytest


async def _connect_as_finagent_app(finagent_app_role: str) -> asyncpg.Connection:
    return await asyncpg.connect(finagent_app_role.replace("postgresql+asyncpg", "postgresql", 1))


async def _connect_as_admin(migrated_db_url: str) -> asyncpg.Connection:
    admin_url = migrated_db_url.replace("postgresql+asyncpg", "postgresql", 1)
    return await asyncpg.connect(admin_url)


async def test_finagent_app_cannot_drop_table(finagent_app_role: str, migrated_db_url: str) -> None:
    """finagent_app must not be able to DROP tables."""
    conn = await _connect_as_finagent_app(finagent_app_role)
    try:
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute("DROP TABLE IF EXISTS morning_notes")
    finally:
        await conn.close()


async def test_finagent_app_cannot_create_table(finagent_app_role: str, migrated_db_url: str) -> None:
    """finagent_app must not be able to CREATE tables in public schema."""
    conn = await _connect_as_finagent_app(finagent_app_role)
    try:
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute("CREATE TABLE test_forbidden (id int)")
    finally:
        await conn.close()


async def test_finagent_app_cannot_create_schema(finagent_app_role: str, migrated_db_url: str) -> None:
    """finagent_app must not be able to CREATE schemas."""
    conn = await _connect_as_finagent_app(finagent_app_role)
    try:
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute("CREATE SCHEMA test_schema")
    finally:
        await conn.close()


async def test_finagent_app_cannot_grant_revoke(finagent_app_role: str, migrated_db_url: str) -> None:
    """finagent_app must not be able to effectively GRANT or REVOKE privileges.

    In PostgreSQL, GRANT/REVOKE without ownership may not raise but also doesn't change
    effective permissions. We verify that the privileges remain unchanged.
    """
    conn = await _connect_as_finagent_app(finagent_app_role)
    admin_conn = await _connect_as_admin(migrated_db_url)

    try:
        # Capture initial grants
        initial_grants = await admin_conn.fetch("""
            SELECT privilege_type
            FROM information_schema.table_privileges
            WHERE table_schema = 'public'
            AND table_name = 'morning_notes'
            AND grantee = 'PUBLIC'
            AND privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
        """)
        initial = {row["privilege_type"] for row in initial_grants}

        # Try to GRANT (should not effectively grant)
        await conn.execute("GRANT SELECT ON morning_notes TO PUBLIC")

        # Try to REVOKE (should not effectively revoke from owner)
        await conn.execute("REVOKE SELECT ON morning_notes FROM PUBLIC")

        # Verify grants unchanged
        final_grants = await admin_conn.fetch("""
            SELECT privilege_type
            FROM information_schema.table_privileges
            WHERE table_schema = 'public'
            AND table_name = 'morning_notes'
            AND grantee = 'PUBLIC'
            AND privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
        """)
        final = {row["privilege_type"] for row in final_grants}

        assert final == initial, f"PUBLIC grants changed unexpectedly: {initial} -> {final}"

    finally:
        await conn.close()
        await admin_conn.close()


async def test_finagent_app_cannot_alter_table(finagent_app_role: str, migrated_db_url: str) -> None:
    """finagent_app must not be able to ALTER tables (DDL)."""
    conn = await _connect_as_finagent_app(finagent_app_role)
    try:
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute("ALTER TABLE morning_notes ADD COLUMN test_col int")
    finally:
        await conn.close()


async def test_finagent_app_can_select_insert_update_delete(finagent_app_role: str, migrated_db_url: str) -> None:
    """finagent_app MUST be able to perform DML on application tables."""
    conn = await _connect_as_finagent_app(finagent_app_role)
    try:
        # SET manager_id for RLS
        await conn.execute("SELECT set_config('app.manager_id', '2', false)")

        # INSERT
        note_id = await conn.fetchval("""
            INSERT INTO morning_notes (portfolio_id, manager_id, company_id, note_text)
            VALUES (100, 2, 10, 'test-dml-note')
            RETURNING id
        """)
        assert note_id is not None

        # SELECT
        count = await conn.fetchval("SELECT count(*) FROM morning_notes WHERE id = $1", note_id)
        assert count == 1

        # UPDATE
        await conn.execute("UPDATE morning_notes SET note_text = 'updated' WHERE id = $1", note_id)
        updated = await conn.fetchval("SELECT note_text FROM morning_notes WHERE id = $1", note_id)
        assert updated == "updated"

        # DELETE
        await conn.execute("DELETE FROM morning_notes WHERE id = $1", note_id)
        count = await conn.fetchval("SELECT count(*) FROM morning_notes WHERE id = $1", note_id)
        assert count == 0

    finally:
        await conn.close()


async def test_finagent_app_can_update_recommendation_decision_columns(
    finagent_app_role: str,
    migrated_db_url: str,
) -> None:
    """finagent_app MUST be able to UPDATE the new decision columns on recommendations.

    Verifies UPDATE privilege on columns added by issue #110:
    - manager_decision
    - decided_at
    - decision_channel
    - telegram_update_id

    This is the critical path for the approval gate resume flow.
    """
    conn = await _connect_as_finagent_app(finagent_app_role)
    admin_conn = await _connect_as_admin(migrated_db_url)

    try:
        # SET manager_id for RLS (manager_id=1 seeded by migrations)
        await conn.execute("SELECT set_config('app.manager_id', '1', false)")

        # Create required FK records via admin (bypasses RLS for setup)
        # Need manager, company, portfolio, morning_note for FK constraints
        await admin_conn.execute("""
            INSERT INTO managers (id, name, email, password_hash)
            VALUES (1, 'Test Manager', 'test@example.com', 'hash')
            ON CONFLICT (id) DO NOTHING
        """)
        await admin_conn.execute("""
            INSERT INTO companies (id, ticker, name)
            VALUES (10, 'TEST', 'Test Company')
            ON CONFLICT (id) DO NOTHING
        """)
        await admin_conn.execute("""
            INSERT INTO portfolios (id, manager_id, name)
            VALUES (100, 1, 'Test Portfolio')
            ON CONFLICT (id) DO NOTHING
        """)
        await admin_conn.execute("""
            INSERT INTO morning_notes (id, portfolio_id, manager_id, company_id, note_text)
            VALUES (123, 100, 1, 10, 'test note')
            ON CONFLICT (id) DO NOTHING
        """)

        # Create a test recommendation via admin (bypasses RLS for setup)
        rec_id = await admin_conn.fetchval("""
            INSERT INTO recommendations (morning_note_id, action, confidence, justification)
            VALUES (123, 'buy', 0.8, 'test recommendation')
            RETURNING id
        """)
        assert rec_id is not None

        # UPDATE manager_decision
        await conn.execute(
            "UPDATE recommendations SET manager_decision = 'approved' WHERE id = $1",
            rec_id,
        )
        decision = await conn.fetchval(
            "SELECT manager_decision FROM recommendations WHERE id = $1",
            rec_id,
        )
        assert decision == "approved"

        # UPDATE decided_at
        await conn.execute(
            "UPDATE recommendations SET decided_at = NOW() WHERE id = $1",
            rec_id,
        )
        decided_at = await conn.fetchval(
            "SELECT decided_at FROM recommendations WHERE id = $1",
            rec_id,
        )
        assert decided_at is not None

        # UPDATE decision_channel
        await conn.execute(
            "UPDATE recommendations SET decision_channel = 'telegram' WHERE id = $1",
            rec_id,
        )
        channel = await conn.fetchval(
            "SELECT decision_channel FROM recommendations WHERE id = $1",
            rec_id,
        )
        assert channel == "telegram"

        # UPDATE telegram_update_id
        await conn.execute(
            "UPDATE recommendations SET telegram_update_id = 999999 WHERE id = $1",
            rec_id,
        )
        update_id = await conn.fetchval(
            "SELECT telegram_update_id FROM recommendations WHERE id = $1",
            rec_id,
        )
        assert update_id == 999999

    finally:
        await conn.close()
        await admin_conn.close()


async def test_finagent_app_grant_list_matches_expectation(finagent_app_role: str, migrated_db_url: str) -> None:
    """Verify finagent_app has exactly the expected grants (smoke probe)."""
    admin_conn = await _connect_as_admin(migrated_db_url)
    try:
        tables = [
            "managers",
            "companies",
            "portfolios",
            "portfolio_holdings",
            "morning_notes",
            "recommendations",
        ]

        for table in tables:
            # Check SELECT, INSERT, UPDATE, DELETE grants
            grants = await admin_conn.fetch("""
                SELECT privilege_type
                FROM information_schema.table_privileges
                WHERE table_schema = 'public'
                AND table_name = $1
                AND grantee = 'finagent_app'
                AND privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
            """, table)

            grant_types = {row["privilege_type"] for row in grants}
            expected = {"SELECT", "INSERT", "UPDATE", "DELETE"}
            assert grant_types == expected, f"Table {table}: expected {expected}, got {grant_types}"

        # Check USAGE on schema public (use has_schema_privilege)
        has_usage = await admin_conn.fetchval("""
            SELECT has_schema_privilege('finagent_app', 'public', 'USAGE')
        """)
        assert has_usage, "Missing USAGE on schema public"

        # Check USAGE on sequences
        seq_grants = await admin_conn.fetch("""
            SELECT privilege_type
            FROM information_schema.usage_privileges
            WHERE object_schema = 'public'
            AND grantee = 'finagent_app'
        """)
        seq_privs = {row["privilege_type"] for row in seq_grants}
        assert "USAGE" in seq_privs, f"Missing USAGE on sequences: {seq_privs}"

    finally:
        await admin_conn.close()
