import logging

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

DECISION_TTL_S = 24 * 3600


def decision_key(run_id: str, rec_id: int) -> str:
    return f"decision:{run_id}:{rec_id}"


async def handle_decision(redis: Redis, run_id: str, rec_id: int, approved: bool) -> bool | None:
    key = decision_key(run_id, rec_id)
    value = "approved" if approved else "rejected"
    first_write = await redis.set(key, value, nx=True, ex=DECISION_TTL_S)
    if not first_write:
        existing = await redis.get(key)
        logger.warning(
            "dupplicate decision ignored",
            extra={"run_id": run_id, "rec_id": rec_id, "existing": existing},
        )
        return None
    return approved
