"""Redis sliding-window rate limiter — 10 req/min per user (CODE_LAB Part 6)."""
import time

from fastapi import HTTPException

from app.config import settings
from app.redis_client import get_redis

WINDOW_SECONDS = 60


def check_rate_limit(user_id: str) -> None:
    limit = settings.rate_limit_per_minute
    r = get_redis()

    if not r:
        return

    now = time.time()
    key = f"rate:{user_id}"

    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
    pipe.zcard(key)
    _, current = pipe.execute()

    if current >= limit:
        oldest = r.zrange(key, 0, 0, withscores=True)
        retry_after = WINDOW_SECONDS
        if oldest:
            retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now))
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": limit,
                "window_seconds": WINDOW_SECONDS,
                "retry_after_seconds": retry_after,
            },
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(retry_after),
            },
        )

    member = f"{now}:{time.time_ns()}"
    pipe = r.pipeline()
    pipe.zadd(key, {member: now})
    pipe.expire(key, WINDOW_SECONDS + 1)
    pipe.execute()
