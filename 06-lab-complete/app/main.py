"""
Arionear RAG Agent — Production (Part 6)

Drug Law RAG chatbot, productionized with:
  Config from env, JSON logging, API Key auth, rate limit, cost guard,
  health/ready, graceful shutdown, stateless Redis sessions, security headers.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import get_redis, ping_redis
from group_project.chatbot.ingest_service import ingest_uploaded_file
from group_project.chatbot.rag_service import chat_with_citation, get_knowledge_base_info

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


def _load_history(session_id: str) -> list[dict]:
    r = get_redis()
    if not r:
        return []
    raw = r.get(f"history:{session_id}")
    return json.loads(raw) if raw else []


def _save_history(session_id: str, history: list[dict]) -> None:
    r = get_redis()
    if not r:
        return
    if len(history) > 20:
        history = history[-20:]
    r.setex(f"history:{session_id}", 3600, json.dumps(history, ensure_ascii=False))


def _append_message(session_id: str, role: str, content: str) -> list[dict]:
    history = _load_history(session_id)
    history.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save_history(session_id, history)
    return history


def _history_for_rag(session_id: str) -> list[dict]:
    """Chỉ role + content cho RAG service."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in _load_history(session_id)
        if m.get("role") in ("user", "assistant")
    ]


def _warmup_rag() -> None:
    """Pre-load embedding model + index để request đầu nhanh hơn."""
    try:
        from src.local_index import ensure_local_index
        from src.task4_chunking_indexing import _get_embedding_model

        ensure_local_index()
        _get_embedding_model()
        logger.info(json.dumps({"event": "rag_warmup", "status": "ok"}))
    except Exception as exc:
        logger.warning(json.dumps({"event": "rag_warmup", "status": "failed", "error": str(exc)}))


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
    _warmup_rag()
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
    sources: list[dict] = Field(default_factory=list)
    retrieval_source: str = "hybrid"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    retrieval_source: str
    session_id: str
    served_by: str


def _run_rag(question: str, session_id: str, user_id: str) -> dict:
    check_rate_limit(user_id)
    check_budget(user_id)

    input_tokens = len(question.split()) * 2
    check_budget(user_id, (input_tokens / 1000) * 0.00015)

    rag_history = _history_for_rag(session_id)
    _append_message(session_id, "user", question)

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": user_id,
        "session_id": session_id,
        "q_len": len(question),
    }))

    result = chat_with_citation(question, history=rag_history)
    answer = result["answer"]
    history = _append_message(session_id, "assistant", answer)

    output_tokens = len(answer.split()) * 2
    record_cost(user_id, input_tokens, output_tokens)

    return {
        "answer": answer,
        "sources": result.get("sources", []),
        "retrieval_source": result.get("retrieval_source", "hybrid"),
        "turn": len([m for m in history if m["role"] == "user"]),
    }


@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "instance": INSTANCE_ID,
        "project": "Arionear — Drug Law RAG Agent",
        "endpoints": {
            "ask": "POST /ask",
            "chat": "POST /api/chat",
            "knowledge_base": "GET /api/knowledge-base",
            "upload": "POST /api/upload",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse)
async def ask_agent(
    body: AskRequest,
    user_id: str = Depends(verify_api_key),
):
    session_id = body.session_id or str(uuid.uuid4())
    result = _run_rag(body.question, session_id, user_id)

    return AskResponse(
        question=body.question,
        answer=result["answer"],
        model=settings.llm_model,
        session_id=session_id,
        turn=result["turn"],
        served_by=INSTANCE_ID,
        timestamp=datetime.now(timezone.utc).isoformat(),
        sources=result["sources"],
        retrieval_source=result["retrieval_source"],
    )


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(
    body: ChatRequest,
    user_id: str = Depends(verify_api_key),
):
    """Alias tương thích frontend React — session lưu Redis nếu có session_id."""
    session_id = body.session_id or str(uuid.uuid4())

    if body.history and not _load_history(session_id):
        seed = [
            {"role": m.role, "content": m.content, "timestamp": datetime.now(timezone.utc).isoformat()}
            for m in body.history
            if m.role in ("user", "assistant")
        ]
        _save_history(session_id, seed[-20:])

    result = _run_rag(body.message, session_id, user_id)
    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        retrieval_source=result["retrieval_source"],
        session_id=session_id,
        served_by=INSTANCE_ID,
    )


@app.get("/api/knowledge-base")
def knowledge_base(_user: str = Depends(verify_api_key)):
    return get_knowledge_base_info()


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    _user: str = Depends(verify_api_key),
):
    if not file.filename:
        return {"success": False, "error": "Tên file không hợp lệ"}

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        return {"success": False, "error": "File quá lớn (tối đa 20MB)"}

    result = ingest_uploaded_file(file.filename, content)
    if result.get("success"):
        result["knowledge_base"] = get_knowledge_base_info()
    return result


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
    kb = get_knowledge_base_info()
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "redis_connected": redis_ok,
        "knowledge_base_chunks": kb.get("total_chunks", 0),
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
    logger.info("Starting %s on %s:%s", settings.app_name, settings.host, settings.port)
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
