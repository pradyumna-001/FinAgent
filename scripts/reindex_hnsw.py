#!/usr/bin/env python3
"""HNSW Reindex Script

Drift detection and REINDEX INDEX CONCURRENTLY for HNSW indexes.
Tracks state in hnsw_reindex_state table.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import asyncpg


DEFAULT_CONFIG = {
    "idx_scan_threshold": 1000,
    "row_count_threshold": 10000,
    "idx_scan_to_row_ratio": 0.1,
    "check_interval_hours": 6,
}


async def get_db_pool() -> asyncpg.Pool:
    db_url = os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL or MIGRATION_DATABASE_URL not set")
    return await asyncpg.create_pool(db_url, min_size=1, max_size=2)


async def get_hnsw_indexes(pool: asyncpg.Pool) -> list[dict]:
    """Get all HNSW indexes in the database."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                i.relname as index_name,
                c.relname as table_name,
                pg_relation_size(i.oid) as index_size_bytes,
                pg_size_pretty(pg_relation_size(i.oid)) as index_size_pretty
            FROM pg_class i
            JOIN pg_index ix ON ix.indexrelid = i.oid
            JOIN pg_class c ON c.oid = ix.indrelid
            JOIN pg_am am ON am.oid = i.relam
            WHERE am.amname = 'hnsw'
            AND c.relkind = 'r'
            ORDER BY i.relname
        """)
        return [dict(r) for r in rows]


async def get_index_stats(pool: asyncpg.Pool, index_name: str) -> Optional[dict]:
    """Get statistics for a specific HNSW index."""
    async with pool.acquire() as conn:
        # Get index scan count and tuples read from pg_stat_user_indexes
        row = await conn.fetchrow("""
            SELECT
                idx_scan,
                idx_tup_read,
                idx_tup_fetch
            FROM pg_stat_user_indexes
            WHERE indexrelname = $1
        """, index_name)
        
        if not row:
            return None
            
        # Get table row count
        table_row = await conn.fetchrow("""
            SELECT c.relname as table_name, c.reltuples::bigint as approx_rows
            FROM pg_class c
            JOIN pg_index ix ON ix.indrelid = c.oid
            JOIN pg_class i ON i.oid = ix.indexrelid
            WHERE i.relname = $1
        """, index_name)
        
        return {
            "idx_scan": row["idx_scan"] or 0,
            "idx_tup_read": row["idx_tup_read"] or 0,
            "idx_tup_fetch": row["idx_tup_fetch"] or 0,
            "approx_rows": int(table_row["approx_rows"]) if table_row else 0,
            "table_name": table_row["table_name"] if table_row else None,
        }


async def get_reindex_state(pool: asyncpg.Pool, index_name: str) -> Optional[dict]:
    """Get current reindex state for an index."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM hnsw_reindex_state WHERE index_name = $1
        """, index_name)
        return dict(row) if row else None


async def upsert_reindex_state(
    pool: asyncpg.Pool,
    index_name: str,
    config: dict,
    **updates
) -> None:
    """Insert or update reindex state."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO hnsw_reindex_state (index_name, config, next_scheduled_at)
            VALUES ($1, $2, now() + interval '1 hour' * $3)
            ON CONFLICT (index_name) DO UPDATE SET
                last_reindex_at = COALESCE($4, hnsw_reindex_state.last_reindex_at),
                last_reindex_duration_ms = COALESCE($5, hnsw_reindex_state.last_reindex_duration_ms),
                last_reindex_rows = COALESCE($6, hnsw_reindex_state.last_reindex_rows),
                last_reindex_idx_scan = COALESCE($7, hnsw_reindex_state.last_reindex_idx_scan),
                last_reindex_tuples_read = COALESCE($8, hnsw_reindex_state.last_reindex_tuples_read),
                last_reindex_status = COALESCE($9, hnsw_reindex_state.last_reindex_status),
                last_error = COALESCE($10, hnsw_reindex_state.last_error),
                next_scheduled_at = COALESCE($11, hnsw_reindex_state.next_scheduled_at),
                config = COALESCE($12, hnsw_reindex_state.config),
                updated_at = now()
        """,
            index_name,
            config,
            config.get("check_interval_hours", 6),
            updates.get("last_reindex_at"),
            updates.get("last_reindex_duration_ms"),
            updates.get("last_reindex_rows"),
            updates.get("last_reindex_idx_scan"),
            updates.get("last_reindex_tuples_read"),
            updates.get("last_reindex_status"),
            updates.get("last_error"),
            updates.get("next_scheduled_at"),
            updates.get("config"),
        )


def check_drift(
    stats: dict,
    state: Optional[dict],
    config: dict
) -> tuple[bool, str]:
    """Check if index needs reindexing based on drift detection."""
    idx_scan = stats["idx_scan"]
    approx_rows = stats["approx_rows"]
    
    if approx_rows < config["row_count_threshold"]:
        return False, f"Row count {approx_rows} below threshold {config['row_count_threshold']}"
    
    if idx_scan < config["idx_scan_threshold"]:
        return False, f"Index scans {idx_scan} below threshold {config['idx_scan_threshold']}"
    
    # Check ratio of index scans to row count
    ratio = idx_scan / approx_rows if approx_rows > 0 else 0
    if ratio < config["idx_scan_to_row_ratio"]:
        return False, f"Idx scan/row ratio {ratio:.4f} below threshold {config['idx_scan_to_row_ratio']}"
    
    # Check if we've reindexed recently
    if state and state.get("last_reindex_at"):
        hours_since_reindex = (datetime.now() - state["last_reindex_at"]).total_seconds() / 3600
        if hours_since_reindex < config["check_interval_hours"]:
            return False, f"Last reindex {hours_since_reindex:.1f}h ago, interval is {config['check_interval_hours']}h"
    
    return True, f"Drift detected: idx_scan={idx_scan}, rows={approx_rows}, ratio={ratio:.4f}"


async def reindex_index(
    pool: asyncpg.Pool,
    index_name: str,
    dry_run: bool = False
) -> tuple[bool, str, int, int]:
    """Run REINDEX INDEX CONCURRENTLY on the index."""
    start = time.perf_counter()
    
    if dry_run:
        return True, "DRY RUN - would run REINDEX INDEX CONCURRENTLY", 0, 0
    
    try:
        async with pool.acquire() as conn:
            # Get row count before
            stats_before = await get_index_stats(pool, index_name)
            rows_before = stats_before["approx_rows"] if stats_before else 0
            
            # Run REINDEX CONCURRENTLY
            await conn.execute(f"REINDEX INDEX CONCURRENTLY {index_name}")
            
            # Get stats after
            stats_after = await get_index_stats(pool, index_name)
            rows_after = stats_after["approx_rows"] if stats_after else 0
            
            duration_ms = int((time.perf_counter() - start) * 1000)
            
            return True, "Reindex completed successfully", duration_ms, rows_after
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return False, f"Reindex failed: {e}", duration_ms, 0


async def run_reindex(
    pool: asyncpg.Pool,
    index_name: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
    config: Optional[dict] = None
) -> list[dict]:
    """Run reindex check and optionally reindex."""
    config = config or DEFAULT_CONFIG
    indexes = await get_hnsw_indexes(pool)
    
    if index_name:
        indexes = [i for i in indexes if i["index_name"] == index_name]
        if not indexes:
            return [{"index_name": index_name, "error": "Index not found"}]
    
    results = []
    
    for idx in indexes:
        idx_name = idx["index_name"]
        print(f"\n--- Checking {idx_name} ---")
        
        stats = await get_index_stats(pool, idx_name)
        state = await get_reindex_state(pool, idx_name)
        
        print(f"  Stats: idx_scan={stats['idx_scan']}, rows≈{stats['approx_rows']}, "
              f"idx_tup_read={stats['idx_tup_read']}")
        
        if state:
            print(f"  State: last_reindex={state.get('last_reindex_at')}, "
                  f"status={state.get('last_reindex_status')}")
        
        needs_reindex, reason = check_drift(stats, state, config)
        print(f"  Drift check: needs_reindex={needs_reindex} ({reason})")
        
        if force:
            needs_reindex = True
            reason = "FORCED reindex"
        
        if needs_reindex:
            success, msg, duration_ms, rows = await reindex_index(pool, idx_name, dry_run)
            
            await upsert_reindex_state(
                pool,
                idx_name,
                config,
                last_reindex_at=datetime.now() if success else None,
                last_reindex_duration_ms=duration_ms if success else None,
                last_reindex_rows=rows if success else None,
                last_reindex_idx_scan=stats["idx_scan"],
                last_reindex_tuples_read=stats["idx_tup_read"],
                last_reindex_status="success" if success else "failed",
                last_error=None if success else msg,
                next_scheduled_at=datetime.now() + timedelta(hours=config["check_interval_hours"]),
            )
            
            results.append({
                "index_name": idx_name,
                "reindexed": True,
                "success": success,
                "message": msg,
                "duration_ms": duration_ms,
                "rows": rows,
            })
            print(f"  Result: {msg}")
        else:
            # Update state with current stats even if no reindex
            await upsert_reindex_state(
                pool,
                idx_name,
                config,
                last_reindex_idx_scan=stats["idx_scan"],
                last_reindex_tuples_read=stats["idx_tup_read"],
            )
            
            results.append({
                "index_name": idx_name,
                "reindexed": False,
                "reason": reason,
            })
            print(f"  Skipped: {reason}")
    
    return results


async def main():
    parser = argparse.ArgumentParser(description="HNSW Index Reindex with Drift Detection")
    parser.add_argument("--index", help="Specific index name to reindex (default: all HNSW indexes)")
    parser.add_argument("--dry-run", action="store_true", help="Check drift but don't actually reindex")
    parser.add_argument("--force", action="store_true", help="Force reindex regardless of drift detection")
    parser.add_argument("--idx-scan-threshold", type=int, default=1000, help="Minimum idx_scan to consider")
    parser.add_argument("--row-count-threshold", type=int, default=10000, help="Minimum row count to consider")
    parser.add_argument("--ratio-threshold", type=float, default=0.1, help="Minimum idx_scan/row ratio")
    parser.add_argument("--interval-hours", type=int, default=6, help="Hours between scheduled reindexes")
    parser.add_argument("--list", action="store_true", help="List all HNSW indexes and exit")
    
    args = parser.parse_args()
    
    config = {
        "idx_scan_threshold": args.idx_scan_threshold,
        "row_count_threshold": args.row_count_threshold,
        "idx_scan_to_row_ratio": args.ratio_threshold,
        "check_interval_hours": args.interval_hours,
    }
    
    pool = await get_db_pool()
    
    try:
        if args.list:
            indexes = await get_hnsw_indexes(pool)
            print("HNSW Indexes:")
            for idx in indexes:
                stats = await get_index_stats(pool, idx["index_name"])
                state = await get_reindex_state(pool, idx["index_name"])
                print(f"  {idx['index_name']} (table: {idx['table_name']}, size: {idx['index_size_pretty']})")
                if stats:
                    print(f"    idx_scan={stats['idx_scan']}, rows≈{stats['approx_rows']}")
                if state:
                    print(f"    last_reindex={state['last_reindex_at']}, status={state['last_reindex_status']}")
            return 0
        
        results = await run_reindex(
            pool,
            index_name=args.index,
            dry_run=args.dry_run,
            force=args.force,
            config=config
        )
        
        print("\n=== Summary ===")
        for r in results:
            if "error" in r:
                print(f"  {r.get('index_name', '?')}: ERROR - {r['error']}")
            elif r.get("reindexed"):
                status = "OK" if r["success"] else "FAILED"
                print(f"  {r['index_name']}: REINDEXED [{status}] - {r['message']} ({r['duration_ms']}ms)")
            else:
                print(f"  {r['index_name']}: SKIPPED - {r['reason']}")
        
        # Exit with error if any forced/needed reindex failed
        failed = [r for r in results if r.get("reindexed") and not r.get("success")]
        return 1 if failed else 0
        
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
        
 
