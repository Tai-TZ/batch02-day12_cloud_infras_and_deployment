# Lab 12 Part 6 — Arionear RAG Agent (Production)

Production-ready **Arionear Drug Law RAG chatbot** — áp dụng toàn bộ concepts Day 12.

**Nhóm Arionear:** Nguyễn Trọng Nguyên, Nguyễn Thành Tài, Ngô Thị Ánh, Nguyễn Hồ Diệu Linh

## Public API URL

> **Deploy URL:** _(điền sau khi deploy Railway/Render)_
>
> Ví dụ: `https://arionear-rag-agent.up.railway.app`

---

## Checklist Deliverable

- [x] Dockerfile (multi-stage, non-root, HEALTHCHECK)
- [x] docker-compose.yml (agent + redis + nginx LB)
- [x] .dockerignore
- [x] Health check (`GET /health`)
- [x] Readiness (`GET /ready`)
- [x] API Key authentication (`X-API-Key`)
- [x] Rate limiting (10 req/min, Redis sliding window)
- [x] Cost guard ($10/month per user, Redis)
- [x] Config từ environment variables
- [x] Structured JSON logging
- [x] Graceful shutdown (SIGTERM)
- [x] Stateless design (conversation history trong Redis)
- [x] RAG agent thật (citation + hybrid retrieval)
- [ ] Public URL hoạt động _(deploy và cập nhật link ở trên)_

---

## Cấu Trúc

```
06-lab-complete/
├── app/
│   ├── main.py           # Production FastAPI entry
│   ├── config.py         # 12-factor config
│   ├── auth.py           # API Key auth
│   ├── rate_limiter.py   # Redis sliding window
│   ├── cost_guard.py     # Monthly budget guard
│   └── redis_client.py   # Shared Redis
├── group_project/chatbot/
│   ├── rag_service.py    # RAG core
│   └── ingest_service.py # Upload → re-index
├── src/                  # RAG pipeline runtime modules
├── data/                 # Knowledge base + chunks.pkl
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── railway.toml
├── render.yaml
└── check_production_ready.py
```

---

## Chạy Local (Backend + UI)

Cần **2 terminal**:

**Terminal 1 — Backend (Docker):**
```bash
cd 06-lab-complete
docker compose up --build --scale agent=3
# Đợi ~60s cho RAG warmup → /health trả 200
```

**Terminal 2 — Frontend (React UI):**
```bash
cd 06-lab-complete/frontend
cp .env.example .env.local   # VITE_AGENT_API_KEY phải khớp AGENT_API_KEY
npm install
npm run dev
# Mở http://localhost:8080
```

Vite proxy `/api` → `http://127.0.0.1:80` (nginx → 3 agent instances).

---

## Chạy Local (chỉ API)

---

## API Endpoints

| Method | Endpoint | Auth | Mô tả |
|--------|----------|------|-------|
| `GET` | `/health` | No | Liveness + KB stats |
| `GET` | `/ready` | No | Readiness (Redis check) |
| `POST` | `/ask` | Yes | RAG Q&A + session (Part 6 lab) |
| `POST` | `/api/chat` | Yes | Alias cho React frontend |
| `GET` | `/api/knowledge-base` | Yes | Thông tin KB |
| `POST` | `/api/upload` | Yes | Upload tài liệu |
| `GET` | `/chat/{session_id}/history` | Yes | Conversation history |

---

## Deploy Railway

```bash
npm i -g @railway/cli
railway login
railway init
railway add --plugin redis          # REDIS_URL tự inject
railway variables set OPENROUTER_API_KEY=sk-or-...
railway variables set AGENT_API_KEY=your-secret-key
railway up
railway domain                       # lấy public URL
```

---

## Deploy Render

1. Push repo lên GitHub
2. Render Dashboard → New → Blueprint → connect repo
3. Set secrets: `OPENROUTER_API_KEY`, `AGENT_API_KEY`, `REDIS_URL`
4. Deploy → copy public URL vào README

---

## Kiểm Tra Production Readiness

```bash
cd 06-lab-complete
python check_production_ready.py
```

---

## Demo Queries

- "Hình phạt cho tội tàng trữ trái phép chất ma túy là gì?"
- "Gần đây có vụ bắt ma túy lớn nào đáng chú ý?"
- "Rapper Bình Vàng dính tội gì?" *(alias → Bình Gold)*
