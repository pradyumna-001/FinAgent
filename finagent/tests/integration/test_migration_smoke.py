import pytest
from ._helpers import fetch_scalar


def test_migrations_apply(migrated_db_url: str) -> None:
    assert "postgresql+asyncpg" in migrated_db_url


@pytest.mark.asyncio
async def test_initial_schema_creates_six_tables(migrated_db_url: str) -> None:
    n = await fetch_scalar(
        migrated_db_url,
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name IN "
        "('managers','companies','portfolios', 'portfolio_holdings','morning_notes', 'recommendations')",
    )
    assert n == 6


@pytest.mark.asyncio
async def test_pgvector_and_embedding_column(migrated_db_url: str) -> None:
    ext = await fetch_scalar(
        migrated_db_url,
        "SELECT extname FROM pg_extension WHERE extname='vector'",
    )
    assert ext == "vector"

    col_type = await fetch_scalar(
        migrated_db_url,
        "SELECT format_type(a.atttypid, a.atttypmod) "
        "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
        "WHERE c.relname='morning_notes' AND a.attname='embedding'",
    )
    assert col_type == "halfvec(2048)"


@pytest.mark.asyncio
async def test_indexes_on_morning_notes(migrated_db_url: str) -> None:
    composite = await fetch_scalar(
        migrated_db_url,
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname='public' AND tablename='morning_notes' "
        "AND indexname='ix_morning_notes_manager_company_date'",
    )
    assert composite is not None
    assert "manager_id" in composite
    assert "company_id" in composite
    assert "generated_at" in composite

    partial = await fetch_scalar(
        migrated_db_url,
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname='public' AND tablename='morning_notes' "
        "AND indexname='idx_morning_notes_completed_at'",
    )
    assert partial is not None
    assert "WHERE" in partial
    assert "status" in partial
    assert "'completed'" in partial
    