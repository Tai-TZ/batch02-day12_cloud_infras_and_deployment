"""Shared Redis connection for stateless session, rate limit, and cost guard."""
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    global _redis
    if not settings.redis_url:
        return None
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def ping_redis() -> bool:
    r = get_redis()
    if not r:
        return False
    try:
        r.ping()
        return True
    except Exception as exc:
        logger.warning("Redis ping failed: %s", exc)
        return False
