# Part 1 — Mission Answers: Localhost vs Production

> Đã hoàn thành và test trên Windows + Python 3.14

---

## Exercise 1.1 — Anti-patterns trong `develop/app.py`

Tìm thấy **8 vấn đề** (≥ 5 yêu cầu):

| # | Vấn đề | Dòng code | Hậu quả |
|---|--------|-----------|---------|
| 1 | **API key hardcode** | `OPENAI_API_KEY = "sk-hardcoded-..."` | Push Git → lộ secret, bị abuse API |
| 2 | **Database password hardcode** | `DATABASE_URL = "postgresql://admin:password123@..."` | Credential lộ trong source code |
| 3 | **Không có config management** | `DEBUG = True`, `MAX_TOKENS = 500` cứng | Không đổi được giữa dev/staging/prod |
| 4 | **Log secret ra console** | `print(f"... Using key: {OPENAI_API_KEY}")` | Log aggregator lưu key → ai cũng đọc được |
| 5 | **Dùng `print()` thay logging** | 3 dòng `print("[DEBUG]...")` | Không parse được, crash Unicode trên Windows |
| 6 | **Không có health check** | Không có `/health`, `/ready` | Cloud platform không biết khi restart |
| 7 | **Host/Port cứng** | `host="localhost"`, `port=8000` | Container/cloud cần `0.0.0.0` + `PORT` env |
| 8 | **Debug reload trong production** | `reload=True` | Tốn tài nguyên, không ổn định khi deploy |

**Bonus phát hiện khi chạy thực tế:** `print()` response tiếng Việt → `UnicodeEncodeError` trên Windows (cp1252) → API trả **500 Internal Server Error**. Production dùng `logger` JSON nên không gặp lỗi này.

---

## Exercise 1.2 — Chạy Basic Version

### Lệnh đã chạy

```powershell
cd 01-localhost-vs-production\develop
pip install -r requirements.txt
$env:PYTHONUTF8 = "1"   # cần trên Windows để tránh lỗi Unicode
python app.py
```

### Kết quả test

| Endpoint | HTTP | Response |
|----------|------|----------|
| `GET /` | 200 | `{"message":"Hello! Agent is running on my machine :)"}` |
| `POST /ask?question=hello` | 200 | `{"answer":"Tôi là AI agent được deploy lên cloud..."}` |
| `GET /health` | **404** | Không tồn tại — đúng anti-pattern |

**Quan sát:** App chạy được trên laptop, nhưng **không production-ready** vì thiếu health check, hardcode secrets, bind `localhost` only.

---

## Exercise 1.3 — So sánh Basic vs Advanced

### Lệnh đã chạy

```powershell
cd ..\production
copy .env.example .env
pip install -r requirements.txt
$env:PYTHONUTF8 = "1"
python app.py
```

### Kết quả test Production

| Endpoint | HTTP | Response |
|----------|------|----------|
| `GET /` | 200 | `{"app":"AI Agent","version":"1.0.0","environment":"development","status":"running"}` |
| `GET /health` | 200 | `{"status":"ok","uptime_seconds":20.5,...}` |
| `GET /ready` | 200 | `{"ready":true}` |
| `POST /ask` (JSON body) | 200 | `{"question":"...","answer":"...","model":"gpt-4o-mini"}` |

Server log production (JSON structured):
```
WARNING:root:OPENAI_API_KEY not set — using mock LLM
INFO: Uvicorn running on http://0.0.0.0:8000
```

### Bảng so sánh (Exercise 1.3)

| Feature | Basic (`develop/`) | Advanced (`production/`) | Tại sao quan trọng? |
|---------|-------------------|---------------------------|---------------------|
| **Config** | Hardcode trong code | `config.py` + `.env` / env vars | Đổi config không sửa code; secrets không vào Git |
| **Secrets** | `OPENAI_API_KEY = "sk-..."` | `os.getenv("OPENAI_API_KEY")` | Tránh lộ key khi push repo |
| **Health check** | Không có (404) | `GET /health` → 200 | Railway/Render/K8s dùng để auto-restart |
| **Readiness** | Không có | `GET /ready` → 200/503 | Load balancer biết khi nào route traffic |
| **Logging** | `print()` debug | JSON structured `logger.info()` | Parse được trong Datadog/Loki; không log secrets |
| **Shutdown** | Tắt đột ngột | `lifespan` + SIGTERM handler | Hoàn thành request trước khi container tắt |
| **Host binding** | `localhost` | `0.0.0.0` (từ `HOST` env) | Container nhận traffic từ bên ngoài |
| **Port** | Cố định `8000` | `PORT` env var | Cloud inject port động (Railway, Render) |
| **Debug reload** | `reload=True` luôn bật | Chỉ khi `DEBUG=true` | Production ổn định, không watch files |
| **CORS** | Không có | Middleware + `ALLOWED_ORIGINS` | Kiểm soát frontend nào được gọi API |
| **Request body** | Query param `?question=` | JSON body `{"question":"..."}` | Chuẩn REST API, dễ mở rộng |
| **Metrics** | Không có | `GET /metrics` | Prometheus scrape uptime/version |

---

## Checkpoint 1 ✅

- [x] Hiểu tại sao hardcode secrets nguy hiểm — push Git = lộ key + log ra console
- [x] Biết cách dùng environment variables — copy `.env.example` → `.env`, đọc qua `config.py`
- [x] Hiểu vai trò health check — `/health` (liveness) vs `/ready` (readiness)
- [x] Biết graceful shutdown là gì — `lifespan` context manager + SIGTERM handler

---

## Câu hỏi thảo luận (README Section 1)

> Nguồn: [README.md](./README.md) — phần "Câu hỏi thảo luận"

### 1. Điều gì xảy ra nếu bạn push code với API key hardcode lên GitHub public?

**Trả lời:**

Ngay khi repo public, bot tự động quét GitHub liên tục để tìm pattern như `sk-...`, `OPENAI_API_KEY`, `password123`. Quy trình thường diễn ra rất nhanh:

1. **Phát hiện** — Bot hoặc attacker tìm thấy key trong commit history (kể cả commit cũ đã xóa key ở HEAD).
2. **Khai thác** — Key bị dùng để gọi API OpenAI/Anthropic thay bạn.
3. **Hậu quả** — Hết quota, phát sinh chi phí lớn, dữ liệu gửi qua API của bạn có thể bị lộ.

Trong lab, `develop/app.py` hardcode:
```python
OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"
```
Nếu đây là key thật và bạn push lên GitHub → coi như key đã **public vĩnh viễn** (Git lưu lịch sử commit).

**Cần làm ngay nếu lỡ lộ key:**
- Revoke/xóa key trên dashboard nhà cung cấp (OpenAI, Anthropic, …)
- Tạo key mới
- **Không** chỉ sửa file rồi commit — phải xóa key khỏi Git history (`git filter-repo`, BFG) hoặc coi key cũ đã chết

**Cách đúng (như `production/`):**
- Key nằm trong env var: `os.getenv("OPENAI_API_KEY")`
- File `.env` nằm trong `.gitignore`, chỉ commit `.env.example` (template không có giá trị thật)
- Không bao giờ log key ra console — `develop/app.py` vi phạm điều này ở dòng `print(f"... Using key: {OPENAI_API_KEY}")`

---

### 2. Tại sao stateless quan trọng khi scale?

**Trả lời:**

**Stateless** nghĩa là mỗi request độc lập — server **không lưu trạng thái** (session, conversation history, cart, …) trong RAM của process.

**Vấn đề khi có state trong memory:**

Giả sử bạn scale lên 3 instance phía sau load balancer:

```
User → Load Balancer → [Agent 1] [Agent 2] [Agent 3]
                              ↓
                    conversation_history = {}  ← mỗi instance một dict riêng
```

- Request 1: user hỏi "Tên tôi là Tai" → vào **Agent 1**, history lưu trong RAM Agent 1
- Request 2: user hỏi "Tên tôi là gì?" → load balancer route sang **Agent 2** → Agent 2 không có history → trả lời sai hoặc "Tôi không biết"

**Giải pháp:** Lưu state ở **nơi dùng chung** — Redis, PostgreSQL, S3 — tất cả instance đều đọc/ghi cùng một chỗ:

```python
# ❌ Anti-pattern — state trong memory
conversation_history = {}

# ✅ Correct — state trong Redis
history = r.lrange(f"history:{user_id}", 0, -1)
```

**Lợi ích khi scale:**
- Thêm/bớt instance tùy ý — không mất data
- Instance chết → instance khác tiếp quản ngay
- Rolling deploy an toàn — tắt từng container không cắt conversation đang diễn ra

Part 1 chưa implement stateless (sẽ học ở Part 5), nhưng `production/app.py` đã chuẩn bị nền tảng: không lưu state in-memory, config từ env, health check để platform biết khi restart instance.

---

### 3. 12-factor nói "dev/prod parity" — nghĩa là gì trong thực tế?

**Trả lời:**

**Dev/prod parity** (nguyên tắc thứ 10 trong [12-Factor App](https://12factor.net/dev-prod-parity)) nghĩa là môi trường **development** và **production** nên **càng giống nhau càng tốt** — về stack, cách config, và hành vi hệ thống.

**Không có parity → "Works on my machine":**

| Khác biệt | Dev (develop/) | Prod thật | Hậu quả |
|-----------|----------------|-----------|---------|
| Host | `localhost` | `0.0.0.0` trong container | Deploy xong không nhận request |
| Port | Cố định `8000` | Cloud inject `PORT=8080` | App crash vì bind sai port |
| Config | Hardcode trong code | Env vars | Giá trị sai trên cloud |
| Health check | Không có | Platform gọi `/health` mỗi 30s | Container bị kill liên tục |
| Logging | `print()` | JSON structured | Không debug được trên cloud |

**Parity trong thực tế nghĩa là:**

1. **Cùng runtime** — Dev cũng chạy qua Docker (Part 2), không chỉ `python app.py` trực tiếp trên Windows
2. **Cùng cách config** — Dùng `.env` / env vars ở cả dev lẫn prod; không hardcode ở dev rồi "sửa sau khi deploy"
3. **Cùng dependencies** — `requirements.txt` / Dockerfile lock version Python và packages
4. **Cùng endpoints** — Dev cũng có `/health`, `/ready` để test trước khi lên cloud
5. **Cùng backing services** — Dev dùng Redis local (Docker), prod dùng Redis cloud — cùng loại service, khác endpoint

**Ví dụ từ lab này:**

Chạy `production/app.py` local với `.env` mô phỏng prod:
```powershell
# .env giống pattern prod
HOST=0.0.0.0
PORT=8000
DEBUG=false
ENVIRONMENT=development
```

→ Khi deploy Railway/Render, chỉ đổi env vars (`PORT`, `AGENT_API_KEY`), **không sửa code** — đó chính là dev/prod parity.

**Mục tiêu:** Bug phát hiện ở dev, không phải lúc 2h sáng production down.

---

## Mẹo Windows

Khi chạy `develop/app.py`, nếu `/ask` trả 500:

```powershell
$env:PYTHONUTF8 = "1"
python app.py
```

Lỗi do `print()` tiếng Việt trên console cp1252 — minh họa thêm tại sao production dùng structured logging thay vì `print()`.
