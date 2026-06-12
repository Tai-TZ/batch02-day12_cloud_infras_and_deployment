"""Monthly cost guard per user — $10/month default (CODE_LAB Part 6)."""
import calendar
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import get_redis

PRICE_PER_1K_INPUT = 0.00015
PRICE_PER_1K_OUTPUT = 0.0006


def _month_key() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


def _budget_key(user_id: str) -> str:
    return f"budget:{user_id}:{_month_key()}"


def _ttl_until_month_end() -> int:
    now = datetime.now(timezone.utc)
    last_day = calendar.monthrange(now.year, now.month)[1]
    end = datetime(now.year, now.month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return max(3600, int((end - now).total_seconds()))


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens / 1000) * PRICE_PER_1K_INPUT
        + (output_tokens / 1000) * PRICE_PER_1K_OUTPUT
    )


def _get_spent(user_id: str) -> float:
    r = get_redis()
    if not r:
        return 0.0
    raw = r.get(_budget_key(user_id))
    return float(raw) if raw else 0.0


def check_budget(user_id: str, estimated_cost: float = 0.0) -> None:
    limit = settings.monthly_budget_usd
    spent = _get_spent(user_id)

    if spent + estimated_cost > limit:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly budget exceeded",
                "spent_usd": round(spent, 4),
                "budget_usd": limit,
                "resets_at": "end of month UTC",
            },
        )


def record_cost(user_id: str, input_tokens: int, output_tokens: int) -> float:
    cost = _estimate_cost(input_tokens, output_tokens)
    r = get_redis()
    if r:
        key = _budget_key(user_id)
        pipe = r.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, _ttl_until_month_end())
        pipe.execute()
    return cost
