"""Redis-backed decision store for approval gate.

Provides idempotent decision recording (approve/reject) per recommendation
using Redis SETNX for exactly-once semantics.
"""

import logging

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

DECISION_TTL_S = 24 * 3600


def decision_key(run_id: str, rec_id: int) -> str:
    """Generate the Redis key for a recommendation decision.

    Args:
        run_id: Pipeline run identifier.
        rec_id: Recommendation database id.

    Returns:
        Redis key in the format "decision:{run_id}:{rec_id}".
    """
    return f"decision:{run_id}:{rec_id}"


async def handle_decision(redis: Redis, run_id: str, rec_id: int, approved: bool) -> bool | None:
    """Record a manager decision idempotently in Redis.

    Uses SET NX (set if not exists) to ensure exactly-once decision recording.
    Returns the decision value on first write, None if a decision was already recorded.

    Args:
        redis: Async Redis client.
        run_id: Pipeline run identifier.
        rec_id: Recommendation database id.
        approved: True for approved, False for rejected.

    Returns:
        True if approved was recorded, False if rejected was recorded,
        None if a decision already existed for this key.
    """
    key = decision_key(run_id, rec_id)
    value = "approved" if approved else "rejected"
    first_write = await redis.set(key, value, nx=True, ex=DECISION_TTL_S)
    if not first_write:
        existing = await redis.get(key)
        logger.warning(
            "duplicate decision ignored",
            extra={"run_id": run_id, "rec_id": rec_id, "existing": existing},
        )
        return None
    return approved
