"""Integration tests for HNSW reindex script."""

import os
import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timedelta

# Add scripts to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from reindex_hnsw import (
    get_hnsw_indexes,
    get_index_stats,
    get_reindex_state,
    upsert_reindex_state,
    check_drift,
    reindex_index,
    run_reindex,
    DEFAULT_CONFIG,
)


class MockConnection:
    """Mock asyncpg connection that supports async context manager."""
    def __init__(self):
        self.fetch = AsyncMock()
        self.fetchrow = AsyncMock()
        self.execute = AsyncMock()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        pass


class MockPool:
    """Mock asyncpg pool that supports async context manager."""
    def __init__(self, conn=None):
        self._conn = conn or MockConnection()
    
    def acquire(self):
        return self._conn


@pytest.fixture
def mock_conn():
    return MockConnection()


@pytest.fixture
def mock_pool(mock_conn):
    return MockPool(mock_conn)


@pytest.mark.asyncio
async def test_get_hnsw_indexes(mock_pool):
    mock_pool._conn.fetch.return_value = [
        {"index_name": "idx_test_hnsw", "table_name": "test_table", "index_size_bytes": 1024, "index_size_pretty": "1 kB"},
    ]
    
    indexes = await get_hnsw_indexes(mock_pool)
    
    assert len(indexes) == 1
    assert indexes[0]["index_name"] == "idx_test_hnsw"
    mock_pool._conn.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_index_stats(mock_pool):
    mock_pool._conn.fetchrow.side_effect = [
        {"idx_scan": 5000, "idx_tup_read": 100000, "idx_tup_fetch": 50000},
        {"table_name": "test_table", "approx_rows": 100000},
    ]
    
    stats = await get_index_stats(mock_pool, "idx_test_hnsw")
    
    assert stats["idx_scan"] == 5000
    assert stats["approx_rows"] == 100000
    assert stats["table_name"] == "test_table"
    assert mock_pool._conn.fetchrow.call_count == 2


@pytest.mark.asyncio
async def test_get_index_stats_not_found(mock_pool):
    mock_pool._conn.fetchrow.return_value = None
    
    stats = await get_index_stats(mock_pool, "nonexistent")
    
    assert stats is None


@pytest.mark.asyncio
async def test_get_reindex_state(mock_pool):
    mock_pool._conn.fetchrow.return_value = {
        "index_name": "idx_test_hnsw",
        "last_reindex_at": "2026-01-01 00:00:00+00",
        "last_reindex_status": "success",
    }
    
    state = await get_reindex_state(mock_pool, "idx_test_hnsw")
    
    assert state["index_name"] == "idx_test_hnsw"
    assert state["last_reindex_status"] == "success"


@pytest.mark.asyncio
async def test_get_reindex_state_not_found(mock_pool):
    mock_pool._conn.fetchrow.return_value = None
    
    state = await get_reindex_state(mock_pool, "nonexistent")
    
    assert state is None


@pytest.mark.asyncio
async def test_upsert_reindex_state(mock_pool):
    await upsert_reindex_state(mock_pool, "idx_test", DEFAULT_CONFIG, last_reindex_status="success")
    
    mock_pool._conn.execute.assert_called_once()
    call_args = mock_pool._conn.execute.call_args[0][0]
    assert "hnsw_reindex_state" in call_args
    assert "ON CONFLICT" in call_args


def test_check_drift_below_row_threshold():
    stats = {"idx_scan": 5000, "approx_rows": 1000}
    state = None
    config = DEFAULT_CONFIG
    
    needs_reindex, reason = check_drift(stats, state, config)
    
    assert needs_reindex is False
    assert "below threshold" in reason


def test_check_drift_below_idx_scan_threshold():
    stats = {"idx_scan": 100, "approx_rows": 100000}
    state = None
    config = DEFAULT_CONFIG
    
    needs_reindex, reason = check_drift(stats, state, config)
    
    assert needs_reindex is False
    assert "below threshold" in reason


def test_check_drift_below_ratio_threshold():
    stats = {"idx_scan": 1000, "approx_rows": 100000}  # ratio = 0.01
    state = None
    config = DEFAULT_CONFIG
    
    needs_reindex, reason = check_drift(stats, state, config)
    
    assert needs_reindex is False
    assert "ratio" in reason


def test_check_drift_recent_reindex():
    stats = {"idx_scan": 50000, "approx_rows": 100000}  # ratio = 0.5 - above threshold
    state = {"last_reindex_at": datetime.now() - timedelta(hours=2)}
    config = DEFAULT_CONFIG
    
    needs_reindex, reason = check_drift(stats, state, config)
    
    assert needs_reindex is False
    assert "ago" in reason


def test_check_drift_triggers_reindex():
    stats = {"idx_scan": 50000, "approx_rows": 100000}  # ratio = 0.5
    state = None
    config = DEFAULT_CONFIG
    
    needs_reindex, reason = check_drift(stats, state, config)
    
    assert needs_reindex is True
    assert "Drift detected" in reason


@pytest.mark.asyncio
async def test_reindex_index_dry_run(mock_pool):
    success, msg, duration, rows = await reindex_index(mock_pool, "idx_test", dry_run=True)
    
    assert success is True
    assert "DRY RUN" in msg
    assert duration == 0
    assert rows == 0
    mock_pool._conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_reindex_index_success(mock_pool):
    # reindex_index calls get_index_stats twice (before and after)
    # Each get_index_stats calls fetchrow twice (pg_stat_user_indexes + pg_class)
    # Total: 4 fetchrow calls
    mock_pool._conn.fetchrow.side_effect = [
        # Before reindex - pg_stat_user_indexes
        {"idx_scan": 5000, "idx_tup_read": 100000, "idx_tup_fetch": 50000},
        # Before reindex - pg_class
        {"table_name": "test_table", "approx_rows": 100000},
        # After reindex - pg_stat_user_indexes
        {"idx_scan": 5000, "idx_tup_read": 100000, "idx_tup_fetch": 50000},
        # After reindex - pg_class
        {"table_name": "test_table", "approx_rows": 100000},
    ]
    
    success, msg, duration, rows = await reindex_index(mock_pool, "idx_test", dry_run=False)
    
    assert success is True
    assert "successfully" in msg
    assert duration >= 0
    assert rows == 100000
    # Should execute REINDEX
    mock_pool._conn.execute.assert_called()


@pytest.mark.asyncio
async def test_reindex_index_failure(mock_pool):
    mock_pool._conn.execute.side_effect = Exception("Lock timeout")
    # Mock get_index_stats call (called once before exception)
    # 2 fetchrow calls
    mock_pool._conn.fetchrow.side_effect = [
        {"idx_scan": 5000, "idx_tup_read": 100000, "idx_tup_fetch": 50000},
        {"table_name": "test_table", "approx_rows": 100000},
    ]
    
    success, msg, duration, rows = await reindex_index(mock_pool, "idx_test", dry_run=False)
    
    assert success is False
    assert "failed" in msg
    assert duration >= 0


@pytest.mark.asyncio
async def test_run_reindex_list_all(mock_pool):
    mock_pool._conn.fetch.return_value = [
        {"index_name": "idx_a", "table_name": "table_a", "index_size_bytes": 1024, "index_size_pretty": "1 kB"},
        {"index_name": "idx_b", "table_name": "table_b", "index_size_bytes": 2048, "index_size_pretty": "2 kB"},
    ]
    # Mock fetchrow to return appropriate data based on the query
    def fetchrow_side_effect(query, *args, **kwargs):
        query_lower = query.lower()
        if "pg_stat_user_indexes" in query_lower:
            return {"idx_scan": 50000, "idx_tup_read": 100000, "idx_tup_fetch": 50000}
        elif "pg_class" in query_lower and "reltuples" in query_lower:
            return {"table_name": "table_a", "approx_rows": 100000}
        elif "hnsw_reindex_state" in query_lower:
            return None
        return None
    
    mock_pool._conn.fetchrow.side_effect = fetchrow_side_effect
    mock_pool._conn.execute.return_value = None
    
    results = await run_reindex(mock_pool, config=DEFAULT_CONFIG)
    
    assert len(results) == 2
    assert results[0]["index_name"] == "idx_a"
    assert results[1]["index_name"] == "idx_b"
    # Both should be reindexed (drift detected)
    assert results[0]["reindexed"] is True
    assert results[1]["reindexed"] is True


@pytest.mark.asyncio
async def test_run_reindex_specific_index(mock_pool):
    mock_pool._conn.fetch.return_value = [
        {"index_name": "idx_target", "table_name": "table_a", "index_size_bytes": 1024, "index_size_pretty": "1 kB"},
    ]
    call_count = [0]
    def fetchrow_side_effect(*args, **kwargs):
        call_count[0] += 1
        c = call_count[0]
        # get_index_stats (2)
        if c == 1:
            return {"idx_scan": 50000, "idx_tup_read": 100000, "idx_tup_fetch": 50000}
        if c == 2:
            return {"table_name": "table_a", "approx_rows": 100000}
        # get_reindex_state (1)
        if c == 3:
            return None
        # reindex before (2)
        if c == 4:
            return {"idx_scan": 50000, "idx_tup_read": 100000, "idx_tup_fetch": 50000}
        if c == 5:
            return {"table_name": "table_a", "approx_rows": 100000}
        # reindex after (2)
        if c == 6:
            return {"idx_scan": 50000, "idx_tup_read": 100000, "idx_tup_fetch": 50000}
        if c == 7:
            return {"table_name": "table_a", "approx_rows": 100000}
        return None
    
    mock_pool._conn.fetchrow.side_effect = fetchrow_side_effect
    
    results = await run_reindex(mock_pool, index_name="idx_target", config=DEFAULT_CONFIG)
    
    assert len(results) == 1
    assert results[0]["index_name"] == "idx_target"
    assert results[0]["reindexed"] is True


@pytest.mark.asyncio
async def test_run_reindex_force_flag(mock_pool):
    mock_pool._conn.fetch.return_value = [
        {"index_name": "idx_test", "table_name": "table_a", "index_size_bytes": 1024, "index_size_pretty": "1 kB"},
    ]
    call_count = [0]
    def fetchrow_side_effect(*args, **kwargs):
        call_count[0] += 1
        c = call_count[0]
        # get_index_stats (2)
        if c == 1:
            return {"idx_scan": 100, "idx_tup_read": 1000, "idx_tup_fetch": 500}
        if c == 2:
            return {"table_name": "table_a", "approx_rows": 1000}
        # get_reindex_state (1)
        if c == 3:
            return None
        # reindex before (2)
        if c == 4:
            return {"idx_scan": 100, "idx_tup_read": 1000, "idx_tup_fetch": 500}
        if c == 5:
            return {"table_name": "table_a", "approx_rows": 1000}
        # reindex after (2)
        if c == 6:
            return {"idx_scan": 100, "idx_tup_read": 1000, "idx_tup_fetch": 500}
        if c == 7:
            return {"table_name": "table_a", "approx_rows": 1000}
        return None
    
    mock_pool._conn.fetchrow.side_effect = fetchrow_side_effect
    mock_pool._conn.execute.return_value = None
    
    results = await run_reindex(mock_pool, index_name="idx_test", force=True, config=DEFAULT_CONFIG)
    
    assert len(results) == 1
    assert results[0]["reindexed"] is True


@pytest.mark.asyncio
async def test_run_reindex_dry_run(mock_pool):
    mock_pool._conn.fetch.return_value = [
        {"index_name": "idx_test", "table_name": "table_a", "index_size_bytes": 1024, "index_size_pretty": "1 kB"},
    ]
    call_count = [0]
    def fetchrow_side_effect(*args, **kwargs):
        call_count[0] += 1
        c = call_count[0]
        # get_index_stats (2)
        if c == 1:
            return {"idx_scan": 50000, "idx_tup_read": 100000, "idx_tup_fetch": 50000}
        if c == 2:
            return {"table_name": "table_a", "approx_rows": 100000}
        # get_reindex_state (1)
        if c == 3:
            return None
        return None
    
    mock_pool._conn.fetchrow.side_effect = fetchrow_side_effect
    
    results = await run_reindex(mock_pool, index_name="idx_test", dry_run=True, config=DEFAULT_CONFIG)
    
    assert len(results) == 1
    assert results[0]["reindexed"] is True
    assert "DRY RUN" in results[0]["message"]
    # Should not execute actual REINDEX
    execute_calls = [c for c in mock_pool._conn.execute.call_args_list if "REINDEX" in str(c)]
    assert len(execute_calls) == 0


@pytest.mark.asyncio
async def test_run_reindex_skips_low_activity(mock_pool):
    """Test that indexes with low activity are skipped."""
    mock_pool._conn.fetch.return_value = [
        {"index_name": "idx_low", "table_name": "table_a", "index_size_bytes": 1024, "index_size_pretty": "1 kB"},
    ]
    call_count = [0]
    def fetchrow_side_effect(*args, **kwargs):
        call_count[0] += 1
        c = call_count[0]
        # get_index_stats (2)
        if c == 1:
            return {"idx_scan": 100, "idx_tup_read": 1000, "idx_tup_fetch": 500}
        if c == 2:
            return {"table_name": "table_a", "approx_rows": 10000}
        # get_reindex_state (1)
        if c == 3:
            return None
        return None
    
    mock_pool._conn.fetchrow.side_effect = fetchrow_side_effect
    
    results = await run_reindex(mock_pool, index_name="idx_low", config=DEFAULT_CONFIG)
    
    assert len(results) == 1
    assert results[0]["reindexed"] is False
    assert "below threshold" in results[0]["reason"]
    # Should not execute REINDEX
    execute_calls = [c for c in mock_pool._conn.execute.call_args_list if "REINDEX" in str(c)]
    assert len(execute_calls) == 0