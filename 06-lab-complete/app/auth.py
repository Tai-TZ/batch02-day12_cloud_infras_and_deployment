"""API Key authentication — maps valid key to user_id."""
from fastapi import Header, HTTPException

from app.config import settings


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    if not x_api_key or x_api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key",
        )
    return x_api_key
