"""
Production AI Agent — Final Project (Part 6)

Combines all Day 12 concepts:
  Config from env, JSON logging, API Key auth, rate limit, cost guard,
  health/ready, graceful shutdown, stateless Redis sessions, security headers.
"""
import os
import time
import signal
import logging
import json
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_budget, record_cost
from app.redis_client import get_redis, ping_redis
from utils.mock_llm import ask as llm_ask

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0
INSTANCE_ID = os.getenv("INSTANCE_ID", f"instance-{uuid.uuid4().hex[:6]}")


# ── Stateless session storage (Redis) ─────────────────────

def _load_history(session_id: str) -> list:
    r = get_redis()
    if not r:
        return []
    raw = r.get(f"history:{session_id}")
    return json.loads(raw) if raw else []


def _save_history(session_id: str, history: list) -> None:
    r = get_redis()
    if not r:
        return
    if len(history) > 20:
        history = history[-20:]
    r.setex(f"history:{session_id}", 3600, json.dumps(history))


def _append_message(session_id: str, role: str, content: str) -> list:
    history = _load_history(session_id)
    history.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save_history(session_id, history)
    return history


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "instance": INSTANCE_ID,
        "redis": bool(settings.redis_url),
    }))
    time.sleep(0.1)
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))
    yield
    _is_ready = False
    logger.info(json.dumps({"event": "shutdown", "instance": INSTANCE_ID}))


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception:
        _error_count += 1
        raise


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    session_id: str
    turn: int
    served_by: str
    timestamp: str


@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "instance": INSTANCE_ID,
        "endpoints": {"ask": "POST /ask", "health": "GET /health", "ready": "GET /ready"},
    }


@app.post("/ask", response_model=AskResponse)
async def ask_agent(
    body: AskRequest,
    request: Request,
    user_id: str = Depends(verify_api_key),
):
    check_rate_limit(user_id)
    check_budget(user_id)

    session_id = body.session_id or str(uuid.uuid4())
    _append_message(session_id, "user", body.question)

    input_tokens = len(body.question.split()) * 2
    check_budget(user_id, (input_tokens / 1000) * 0.00015)

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": user_id,
        "session_id": session_id,
        "q_len": len(body.question),
    }))

    answer = llm_ask(body.question)
    history = _append_message(session_id, "assistant", answer)

    output_tokens = len(answer.split()) * 2
    record_cost(user_id, input_tokens, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        session_id=session_id,
        turn=len([m for m in history if m["role"] == "user"]),
        served_by=INSTANCE_ID,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/chat/{session_id}/history")
def get_history(session_id: str, _user: str = Depends(verify_api_key)):
    history = _load_history(session_id)
    if not history:
        raise HTTPException(404, "Session not found or expired")
    return {"session_id": session_id, "messages": history, "count": len(history)}


@app.get("/health")
def health():
    redis_ok = ping_redis() if settings.redis_url else None
    status = "ok" if (redis_ok is not False) else "degraded"
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "redis_connected": redis_ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def ready():
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    if settings.redis_url and not ping_redis():
        raise HTTPException(503, "Redis not available")
    return {"ready": True, "instance": INSTANCE_ID}


@app.get("/metrics")
def metrics(_user: str = Depends(verify_api_key)):
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "instance": INSTANCE_ID,
    }


def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
