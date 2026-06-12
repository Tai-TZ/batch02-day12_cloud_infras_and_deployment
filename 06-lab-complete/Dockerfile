# ============================================================
# Arionear RAG Agent — slim cloud image (~300 MB, no CUDA)
# BM25 retrieval + OpenRouter LLM (SKIP_LOCAL_EMBEDDINGS=true)
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.11-slim AS runtime

RUN groupadd -r agent && useradd -r -g agent -d /app agent

WORKDIR /app

COPY --from=builder /root/.local /app/.local

COPY app/ ./app/
COPY src/ ./src/
COPY group_project/ ./group_project/
COPY data/ ./data/

RUN chown -R agent:agent /app

USER agent

ENV PYTHONUSERBASE=/app/.local
ENV PATH=/app/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SKIP_LOCAL_EMBEDDINGS=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c \
    "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\",\"8000\")}/health')" \
    || exit 1

CMD ["/bin/sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
