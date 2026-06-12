# Day 12 Code Lab — Solution (Part 1–5)

> **Sinh viên:** Nguyễn Thành Tài  
> **Lab:** AICB-P1 · Cloud Infrastructure & Deployment  
> **Nguồn:** Gom nguyên văn từ `MISSION_ANSWERS.md` của từng part

---

# Part 1 — Mission Answers: Localhost vs Production

## Exercise 1.1 — Anti-patterns trong `develop/app.py`

Tìm thấy **8 vấn đề** (≥ 5 yêu cầu):


| #   | Vấn đề                            | Dòng code                                             | Hậu quả                                      |
| --- | --------------------------------- | ----------------------------------------------------- | -------------------------------------------- |
| 1   | **API key hardcode**              | `OPENAI_API_KEY = "sk-hardcoded-..."`                 | Push Git → lộ secret, bị abuse API           |
| 2   | **Database password hardcode**    | `DATABASE_URL = "postgresql://admin:password123@..."` | Credential lộ trong source code              |
| 3   | **Không có config management**    | `DEBUG = True`, `MAX_TOKENS = 500` cứng               | Không đổi được giữa dev/staging/prod         |
| 4   | **Log secret ra console**         | `print(f"... Using key: {OPENAI_API_KEY}")`           | Log aggregator lưu key → ai cũng đọc được    |
| 5   | **Dùng `print()` thay logging**   | 3 dòng `print("[DEBUG]...")`                          | Không parse được, crash Unicode trên Windows |
| 6   | **Không có health check**         | Không có `/health`, `/ready`                          | Cloud platform không biết khi restart        |
| 7   | **Host/Port cứng**                | `host="localhost"`, `port=8000`                       | Container/cloud cần `0.0.0.0` + `PORT` env   |
| 8   | **Debug reload trong production** | `reload=True`                                         | Tốn tài nguyên, không ổn định khi deploy     |


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


| Endpoint                   | HTTP    | Response                                                 |
| -------------------------- | ------- | -------------------------------------------------------- |
| `GET /`                    | 200     | `{"message":"Hello! Agent is running on my machine :)"}` |
| `POST /ask?question=hello` | 200     | `{"answer":"Tôi là AI agent được deploy lên cloud..."}`  |
| `GET /health`              | **404** | Không tồn tại — đúng anti-pattern                        |


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


| Endpoint                | HTTP | Response                                                                              |
| ----------------------- | ---- | ------------------------------------------------------------------------------------- |
| `GET /`                 | 200  | `{"app":"AI Agent","version":"1.0.0","environment":"development","status":"running"}` |
| `GET /health`           | 200  | `{"status":"ok","uptime_seconds":20.5,...}`                                           |
| `GET /ready`            | 200  | `{"ready":true}`                                                                      |
| `POST /ask` (JSON body) | 200  | `{"question":"...","answer":"...","model":"gpt-4o-mini"}`                             |


Server log production (JSON structured):

```
WARNING:root:OPENAI_API_KEY not set — using mock LLM
INFO: Uvicorn running on http://0.0.0.0:8000
```

### Bảng so sánh (Exercise 1.3)


| Feature          | Basic (`develop/`)          | Advanced (`production/`)        | Tại sao quan trọng?                              |
| ---------------- | --------------------------- | ------------------------------- | ------------------------------------------------ |
| **Config**       | Hardcode trong code         | `config.py` + `.env` / env vars | Đổi config không sửa code; secrets không vào Git |
| **Secrets**      | `OPENAI_API_KEY = "sk-..."` | `os.getenv("OPENAI_API_KEY")`   | Tránh lộ key khi push repo                       |
| **Health check** | Không có (404)              | `GET /health` → 200             | Railway/Render/K8s dùng để auto-restart          |
| **Readiness**    | Không có                    | `GET /ready` → 200/503          | Load balancer biết khi nào route traffic         |
| **Logging**      | `print()` debug             | JSON structured `logger.info()` | Parse được trong Datadog/Loki; không log secrets |
| **Shutdown**     | Tắt đột ngột                | `lifespan` + SIGTERM handler    | Hoàn thành request trước khi container tắt       |
| **Host binding** | `localhost`                 | `0.0.0.0` (từ `HOST` env)       | Container nhận traffic từ bên ngoài              |
| **Port**         | Cố định `8000`              | `PORT` env var                  | Cloud inject port động (Railway, Render)         |
| **Debug reload** | `reload=True` luôn bật      | Chỉ khi `DEBUG=true`            | Production ổn định, không watch files            |
| **CORS**         | Không có                    | Middleware + `ALLOWED_ORIGINS`  | Kiểm soát frontend nào được gọi API              |
| **Request body** | Query param `?question=`    | JSON body `{"question":"..."}`  | Chuẩn REST API, dễ mở rộng                       |
| **Metrics**      | Không có                    | `GET /metrics`                  | Prometheus scrape uptime/version                 |


---

## Checkpoint 1 ✅

- Hiểu tại sao hardcode secrets nguy hiểm — push Git = lộ key + log ra console
- Biết cách dùng environment variables — copy `.env.example` → `.env`, đọc qua `config.py`
- Hiểu vai trò health check — `/health` (liveness) vs `/ready` (readiness)
- Biết graceful shutdown là gì — `lifespan` context manager + SIGTERM handler

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


| Khác biệt    | Dev (develop/)      | Prod thật                      | Hậu quả                        |
| ------------ | ------------------- | ------------------------------ | ------------------------------ |
| Host         | `localhost`         | `0.0.0.0` trong container      | Deploy xong không nhận request |
| Port         | Cố định `8000`      | Cloud inject `PORT=8080`       | App crash vì bind sai port     |
| Config       | Hardcode trong code | Env vars                       | Giá trị sai trên cloud         |
| Health check | Không có            | Platform gọi `/health` mỗi 30s | Container bị kill liên tục     |
| Logging      | `print()`           | JSON structured                | Không debug được trên cloud    |


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

---

# Part 2 — Mission Answers: Docker Containerization

---

## Exercise 2.1 — Dockerfile cơ bản (`develop/Dockerfile`)

### Câu trả lời


| #   | Câu hỏi                                  | Trả lời                                                                                                                                                                                                     |
| --- | ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Base image là gì?**                    | `python:3.11` — full Python distribution (~1 GB), có đầy đủ tools                                                                                                                                           |
| 2   | **Working directory là gì?**             | `/app` — mọi lệnh COPY/RUN/CMD chạy trong thư mục này                                                                                                                                                       |
| 3   | **Tại sao COPY requirements.txt trước?** | Tận dụng **Docker layer cache**: dependencies ít đổi → layer `pip install` được cache; chỉ sửa code thì không cài lại pip                                                                                   |
| 4   | **CMD vs ENTRYPOINT khác nhau thế nào?** | **CMD** = lệnh mặc định, dễ override khi `docker run ... python other.py`. **ENTRYPOINT** = entry point cố định, args từ `docker run` được **append** vào — phù hợp khi container luôn chạy cùng một binary |


---

## Exercise 2.2 — Build và run Basic

### Lệnh đã chạy (từ **root repo**)

```powershell
cd batch02-day12_cloud_infras_and_deployment   # root repo

docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run --rm -d -p 8000:8000 --name my-agent-develop my-agent:develop
```

### Kết quả test


| Endpoint                            | HTTP | Response                                                |
| ----------------------------------- | ---- | ------------------------------------------------------- |
| `GET /health`                       | 200  | `{"status":"ok","uptime_seconds":...,"container":true}` |
| `POST /ask?question=What+is+Docker` | 200  | `{"answer":"Container là cách đóng gói app..."}`        |
| `GET /`                             | 200  | `{"message":"Agent is running in a Docker container!"}` |


### Image size

```
REPOSITORY:TAG      SIZE
my-agent:develop    1.66GB    ← python:3.11 full image
```

**Quan sát:** Image rất lớn vì dùng `python:3.11` (full), không multi-stage, chứa cả build tools không cần khi runtime.

---

## Exercise 2.3 — Multi-stage build (`production/Dockerfile`)

### Phân tích 2 stages


| Stage | Tên         | Base image         | Làm gì?                                                                                          |
| ----- | ----------- | ------------------ | ------------------------------------------------------------------------------------------------ |
| 1     | **builder** | `python:3.11-slim` | Cài `gcc`, `libpq-dev`; `pip install --user` dependencies                                        |
| 2     | **runtime** | `python:3.11-slim` | Copy `/root/.local` từ builder; copy `main.py` + `mock_llm.py`; chạy **non-root user** `appuser` |


### Tại sao image nhỏ hơn?

1. **Slim base** — `python:3.11-slim` (~~150 MB) thay vì full (~~1 GB)
2. **Không copy build tools** — gcc, apt cache ở stage builder, không vào final image
3. **Chỉ copy site-packages** — không copy source pip cache, không copy builder layer

### Build và so sánh

```powershell
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images my-agent --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
```

```
REPOSITORY:TAG      SIZE
my-agent:advanced   236MB     ← giảm ~85% so với develop
my-agent:develop    1.66GB
```

**Bonus trong production Dockerfile:**

- `USER appuser` — security best practice
- `HEALTHCHECK` — Docker tự monitor container
- `CMD uvicorn ... --workers 2` — production server thay vì `python app.py`

---

## Exercise 2.4 — Docker Compose stack

### Architecture diagram

```
                    ┌─────────────┐
                    │   Client    │
                    │  (browser/  │
                    │    curl)    │
                    └──────┬──────┘
                           │ :80
                           ▼
                    ┌─────────────┐
                    │    Nginx    │  Reverse proxy + rate limit (10 req/s)
                    │  (port 80)  │
                    └──────┬──────┘
                           │ agent:8000 (internal network)
                           ▼
                    ┌─────────────┐
                    │    Agent    │  FastAPI + uvicorn (2 workers)
                    │  (no public │  ENV: REDIS_URL, QDRANT_URL
                    │    port)    │
                    └───┬────┬────┘
                        │    │
           redis:6379 ◄─┘    └─► qdrant:6333
                │                      │
         ┌──────┴──────┐        ┌─────┴─────┐
         │    Redis    │        │   Qdrant   │
         │  (session/  │        │  (vector   │
         │ rate limit) │        │    DB)     │
         └─────────────┘        └────────────┘

Network: production_internal (bridge — isolated)
Volumes: redis_data, qdrant_data (persistent)
```

### Lệnh đã chạy

```powershell
cd 02-docker\production
# Tạo .env.local (secrets, không commit git)
docker compose up -d --build
docker compose ps
```

### 4 Services được start


| Service    | Image                  | Port public      | Vai trò                               |
| ---------- | ---------------------- | ---------------- | ------------------------------------- |
| **nginx**  | `nginx:alpine`         | `80`, `443`      | Entry point — proxy request vào agent |
| **agent**  | build từ Dockerfile    | internal `:8000` | FastAPI AI agent                      |
| **redis**  | `redis:7-alpine`       | internal `:6379` | Cache session, rate limiting          |
| **qdrant** | `qdrant/qdrant:v1.9.0` | internal `:6333` | Vector database cho RAG               |


### Cách communicate

- Tất cả services cùng network `internal` (Docker DNS)
- Agent gọi Redis: `redis://redis:6379/0` (hostname = tên service)
- Agent gọi Qdrant: `http://qdrant:6333`
- Client **chỉ** truy cập Nginx `:80` → Nginx proxy sang `agent:8000`
- `depends_on` + `condition: service_healthy` — agent chỉ start khi redis + qdrant healthy

### Kết quả test qua Nginx


| Test                               | HTTP | Response                                    |
| ---------------------------------- | ---- | ------------------------------------------- |
| `GET http://localhost/health`      | 200  | `{"status":"ok","uptime_seconds":13.7,...}` |
| `POST http://localhost/ask` (JSON) | 200  | `{"answer":"..."}`                          |


```powershell
Invoke-RestMethod -Uri "http://localhost/ask" -Method POST `
  -ContentType "application/json" `
  -Body '{"question": "Explain microservices"}'
```

### Debug container

```powershell
# Xem logs
docker compose logs agent
docker compose logs nginx

# Exec vào container
docker exec production-agent-1 python -c "import os; print(os.getenv('REDIS_URL'))"
# → redis://redis:6379/0

# Dừng stack
docker compose down
```

---

## Checkpoint 2 ✅

- Hiểu cấu trúc Dockerfile (FROM, WORKDIR, COPY, RUN, EXPOSE, CMD)
- Biết lợi ích multi-stage builds — 1.66 GB → 236 MB
- Hiểu Docker Compose orchestration — 4 services, internal network
- Biết debug: `docker compose logs`, `docker exec`

---

## Câu hỏi thảo luận (README Section 2)

> Nguồn: [README.md](./README.md) — phần "Câu hỏi thảo luận"

### 1. Tại sao `COPY requirements.txt .` rồi `RUN pip install` TRƯỚC khi `COPY . .`?

**Trả lời:**

Docker build image theo **layers** — mỗi instruction (FROM, COPY, RUN) tạo một layer. Khi rebuild, Docker **cache** layer nếu instruction và input không đổi.

**Thứ tự tối ưu:**

```dockerfile
COPY requirements.txt .      # Layer A — ít thay đổi
RUN pip install -r requirements.txt   # Layer B — cache nếu requirements.txt không đổi
COPY app.py .                # Layer C — thay đổi thường xuyên khi dev
```

**Khi bạn sửa `app.py`:**

- Layer A, B **dùng cache** → không chạy lại `pip install` (~30 giây tiết kiệm)
- Chỉ rebuild Layer C

**Nếu làm ngược (`COPY . .` trước):**

```dockerfile
COPY . .                     # Mọi thay đổi code → layer này invalid
RUN pip install ...          # Phải cài lại pip MỖI LẦN sửa 1 dòng code
```

→ Build chậm, lãng phí bandwidth CI/CD.

**Nguyên tắc:** Copy file **ít thay đổi** trước, file **hay thay đổi** sau.

---

### 2. `.dockerignore` nên chứa những gì? Tại sao `venv/` và `.env` quan trọng?

**Trả lời:**

`.dockerignore` loại file khỏi **build context** (file gửi lên Docker daemon khi `docker build`). Tương tự `.gitignore` nhưng cho Docker build.

**Nên ignore (từ `develop/.dockerignore`):**


| Pattern                   | Lý do                                                                          |
| ------------------------- | ------------------------------------------------------------------------------ |
| `venv/`, `.venv/`, `env/` | Virtual env local ~hàng trăm MB, không cần trong container (pip install riêng) |
| `.env`, `.env.`*          | **Secrets** — API keys, passwords; đưa vào image = lộ vĩnh viễn trong layer    |
| `__pycache__/`, `*.pyc`   | Bytecode local, không cần, gây conflict                                        |
| `.git/`                   | Toàn bộ git history — tăng context size vô ích                                 |
| `*.md`, `tests/`, `docs/` | Không cần cho runtime                                                          |
| `.vscode/`, `.idea/`      | IDE config                                                                     |


**Tại sao `venv/` quan trọng:**

- Windows venv có binary không tương thích Linux container → build fail hoặc chạy sai
- Làm context upload chậm (có thể GB)
- Container phải tự `pip install` đúng OS/architecture

**Tại sao `.env` quan trọng:**

- Docker layer **immutable** — secret bake vào image sẽ tồn tại mãi dù xóa file sau
- Ai pull image từ registry đều extract được secret: `docker history`, `docker save`
- **Đúng cách:** inject secrets lúc **runtime** qua `env_file`, `-e`, hoặc Docker secrets — như `docker-compose.yml` dùng `.env.local`

---

### 3. Nếu agent cần đọc file từ disk, làm sao mount volume vào container?

**Trả lời:**

Có 2 loại volume chính:

#### A. Bind mount — map thư mục host vào container

Dùng khi dev (hot reload) hoặc đọc file từ máy host:

```powershell
# Mount folder ./data trên host → /app/data trong container
docker run -p 8000:8000 `
  -v "${PWD}/data:/app/data:ro" `
  my-agent:develop
```

```yaml
# docker-compose.yml
services:
  agent:
    volumes:
      - ./documents:/app/documents:ro   # :ro = read-only
```

Agent code đọc file:

```python
with open("/app/documents/report.pdf", "rb") as f:
    content = f.read()
```

#### B. Named volume — Docker quản lý storage (production)

Dùng cho data persistent (database, cache) — như trong lab:

```yaml
# docker-compose.yml (đã có sẵn)
services:
  redis:
    volumes:
      - redis_data:/data      # Named volume

  qdrant:
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  redis_data:                 # Docker tạo và quản lý
  qdrant_data:
```

**So sánh:**


|          | Bind mount              | Named volume                                   |
| -------- | ----------------------- | ---------------------------------------------- |
| Path     | Bạn chọn path host      | Docker quản lý (`/var/lib/docker/volumes/...`) |
| Dùng khi | Dev, đọc file local     | Production DB, persistent data                 |
| Portable | Phụ thuộc path máy host | Portable giữa máy                              |


**Ví dụ thực tế cho AI agent:**

```yaml
services:
  agent:
    volumes:
      - ./knowledge-base:/app/knowledge:ro    # PDF/docs để RAG
      - agent_uploads:/app/uploads            # User uploads persistent
volumes:
  agent_uploads:
```

**Lưu ý:**

- Dùng `:ro` (read-only) khi container chỉ đọc, không ghi — bảo mật hơn
- Không mount `.env` — dùng `env_file:` thay thế
- Trên Windows: path `-v C:\Users\Tai\data:/app/data` hoạt động với Docker Desktop

---

## Ghi chú khi chạy trên máy này

1. **Build từ root repo** — Dockerfile copy `utils/mock_llm.py` từ project root
2. **Tạo `.env.local`** trước khi `docker compose up` (file không commit git)
3. **Qdrant healthcheck** — image không có `curl`; đã sửa dùng bash TCP check `/readyz`
4. **POST /ask** — production dùng JSON body, không phải query param
5. **Stack đang chạy** — `docker compose ps` tại `02-docker/production/` để kiểm tra

---

# Part 3 — Mission Answers: Cloud Deployment

---

## Exercise 3.1 — Deploy Railway

### Thư mục làm việc

```
03-cloud-deployment/railway/
├── app.py
├── railway.toml
├── requirements.txt
└── utils/mock_llm.py
```

**Luôn `cd` vào folder `railway/`** trước khi chạy lệnh Railway CLI.

### Các bước đã thực hiện

```powershell
cd 03-cloud-deployment\railway

npm i -g @railway/cli
railway login
railway init                    # Tạo project: day12-ai-agent
railway up                      # ⚠️ Phải chạy TRƯỚC variables (tạo service)
railway variables set ENVIRONMENT=production
railway variables set AGENT_API_KEY=my-secret-key
railway domain
```

### Lỗi đã gặp và cách sửa


| Lỗi                                | Nguyên nhân                                          | Cách sửa                                               |
| ---------------------------------- | ---------------------------------------------------- | ------------------------------------------------------ |
| `Project has no services`          | `railway init` chỉ tạo project rỗng, chưa có service | Chạy `**railway up` trước**, rồi mới `variables set`   |
| Terminal bị chiếm sau `railway up` | CLI stream logs liên tục                             | Mở **terminal mới** hoặc `Ctrl+C` (app cloud vẫn chạy) |


### Thông tin deploy


| Mục           | Giá trị                                                                                                        |
| ------------- | -------------------------------------------------------------------------------------------------------------- |
| Project       | `day12-ai-agent`                                                                                               |
| Platform      | Railway (Nixpacks builder)                                                                                     |
| Public URL    | [https://day12-ai-agent-production-c259.up.railway.app](https://day12-ai-agent-production-c259.up.railway.app) |
| Start command | `uvicorn app:app --host 0.0.0.0 --port $PORT`                                                                  |
| Health check  | `/health` (Railway restart nếu fail)                                                                           |


### Kết quả test (public URL)


| Endpoint      | HTTP | Response                                                                |
| ------------- | ---- | ----------------------------------------------------------------------- |
| `GET /health` | 200  | `{"status":"ok","platform":"Railway","uptime_seconds":371.3,...}`       |
| `GET /`       | 200  | `{"message":"AI Agent running on Railway!","docs":"/docs",...}`         |
| `POST /ask`   | 200  | `{"question":"Hello from Railway","answer":"...","platform":"Railway"}` |


```powershell
curl.exe https://day12-ai-agent-production-c259.up.railway.app/health

Invoke-RestMethod -Uri "https://day12-ai-agent-production-c259.up.railway.app/ask" `
  -Method POST -ContentType "application/json" `
  -Body '{"question": "Hello from Railway"}'
```

### Xem logs

```powershell
cd 03-cloud-deployment\railway
railway logs
```

Hoặc Dashboard: [https://railway.com/project/e30946db-99aa-45bf-8f5a-a777d4f40d80](https://railway.com/project/e30946db-99aa-45bf-8f5a-a777d4f40d80)

---

## Exercise 3.2 — Render (Optional, không làm)

Lab chỉ yêu cầu **1 platform** → Railway đủ. Nếu muốn tham khảo sau:

- Folder `render/` chỉ có `render.yaml` (Infrastructure as Code)
- Deploy qua GitHub → Render Blueprint
- So sánh nhanh với Railway:


|           | Railway          | Render                           |
| --------- | ---------------- | -------------------------------- |
| Deploy    | CLI `railway up` | Git push + Blueprint             |
| Config    | `railway.toml`   | `render.yaml`                    |
| Free tier | $5 credit        | 750h/tháng (có sleep/cold start) |


---

## Exercise 3.3 — Cloud Run (Optional, đọc hiểu)

Đọc 2 file trong `production-cloud-run/`:

`**cloudbuild.yaml`** — CI/CD pipeline:

```
push code → pytest → docker build → push GCR → deploy Cloud Run
```

`**service.yaml**` — định nghĩa service:

- Autoscaling min=1, max=10
- Health: liveness `/health`, startup `/ready`
- Secrets từ GCP Secret Manager (không hardcode)

Không bắt buộc deploy cho Part 3.

---

## Checkpoint 3 ✅

- Deploy thành công lên ít nhất 1 platform (Railway)
- Có public URL hoạt động
- Hiểu cách set environment variables (`railway variables set` / Dashboard)
- Biết cách xem logs (`railway logs`)

---

## Câu hỏi thảo luận (README Section 3)

> Nguồn: [README.md](./README.md) — phần "Câu hỏi thảo luận"

### 1. Tại sao serverless (Lambda) không phải lúc nào cũng tốt cho AI agent?

**Trả lời:**

**Serverless** (AWS Lambda, Azure Functions) = function chạy theo event, tự scale, trả tiền theo lần gọi. Nghe hấp dẫn nhưng **AI agent** thường không phù hợp vì:


| Hạn chế Lambda                   | Ảnh hưởng với AI agent                                              |
| -------------------------------- | ------------------------------------------------------------------- |
| **Timeout** (thường max 15 phút) | LLM call dài, RAG pipeline, streaming dễ vượt giới hạn              |
| **Cold start**                   | Mỗi lần wake up phải load Python + dependencies → user chờ vài giây |
| **Không giữ state**              | Conversation history phải ở Redis/DB bên ngoài — thêm complexity    |
| **Payload size limit**           | Upload file lớn (PDF cho RAG) bị giới hạn                           |
| **WebSocket / streaming**        | Streaming token từ LLM khó implement hơn long-running server        |
| **Memory limit**                 | Load model embedding lớn có thể không đủ RAM                        |


**Khi nào Lambda OK:** Trigger đơn giản (1 câu hỏi → 1 câu trả lời ngắn, không streaming, không file lớn).

**Khi nào dùng container** (Railway, Render, Cloud Run — như lab này):

- Agent chạy liên tục như một **web server** (FastAPI + uvicorn)
- Hỗ trợ streaming, WebSocket, long request
- Health check `/health` — platform biết khi restart

→ Lab chọn **Railway (container)** thay vì Lambda là lựa chọn đúng cho AI agent API.

---

### 2. "Cold start" là gì? Ảnh hưởng thế nào đến UX?

**Trả lời:**

**Cold start** = thời gian từ lúc user gửi request đầu tiên đến khi app **sẵn sàng xử lý**, vì instance/container đang **sleep hoặc chưa tồn tại**.

**Quy trình cold start:**

```
User gửi request
    → Platform nhận thấy không có instance đang chạy
    → Khởi động container mới
    → Cài/load dependencies, start uvicorn
    → Mới xử lý request  ← user đã chờ 5–60 giây
```

**Ảnh hưởng UX:**


| Platform                    | Cold start                           | Trải nghiệm user             |
| --------------------------- | ------------------------------------ | ---------------------------- |
| Render free                 | ~30–60 giây                          | User tưởng app bị lỗi, bỏ đi |
| Railway                     | Vài giây (hoặc không nếu có traffic) | Chấp nhận được               |
| Cloud Run (min-instances=0) | 2–10 giây                            | Hơi chậm request đầu         |
| Cloud Run (min-instances=1) | Không cold start                     | Luôn nhanh, tốn tiền hơn     |


**Ví dụ thực tế:** Chatbot AI — user mở app, gõ câu hỏi, chờ 45 giây mới có reply → UX rất tệ.

**Cách giảm cold start:**

- Dùng platform giữ instance warm (Railway, paid plan)
- Set `min-instances=1` (Cloud Run)
- Ping `/health` định kỳ (cron job) để giữ app awake — hack, không khuyến nghị production

**Railway deploy của bạn:** Sau deploy đầu, app thường **warm** — request `/health` trả ngay ~200ms. Cold start chủ yếu gặp sau thời gian idle lâu hoặc platform free tier sleep.

---

### 3. Khi nào nên upgrade từ Railway lên Cloud Run?

**Trả lời:**

**Railway đủ khi:**

- MVP, demo, lab, side project (như Part 3 này)
- Team nhỏ, cần deploy nhanh (`railway up`)
- Traffic thấp–trung bình
- Không cần compliance/IAM phức tạp

**Nên upgrade lên Cloud Run khi:**


| Nhu cầu                        | Railway               | Cloud Run                                             |
| ------------------------------ | --------------------- | ----------------------------------------------------- |
| **Traffic lớn, unpredictable** | Scale hạn chế         | Autoscale 0→N, fine-grained                           |
| **CI/CD production**           | Basic                 | `cloudbuild.yaml`: test → build → deploy tự động      |
| **Security/compliance**        | Đơn giản              | IAM, VPC, Secret Manager, audit logs                  |
| **Multi-region**               | Hạn chế               | Deploy nhiều region (asia-southeast1, us-central1...) |
| **Cost control chi tiết**      | $5 credit rồi trả phí | Pay-per-request, min-instances tuning                 |
| **SLA / uptime**               | Side project level    | Production SLA với GCP                                |
| **Tích hợp GCP**               | Không                 | BigQuery, Cloud Storage, Vertex AI...                 |


**Quy tắc thực tế:**

```
Idea → Railway/Render     (validate, demo)
    ↓ có users thật
Production → Cloud Run/AWS  (scale, security, CI/CD)
    ↓ rất lớn
Enterprise → Kubernetes     (multi-team, multi-service)
```

**Lab Day 12:** Railway = Tier 1 (học deploy). `production-cloud-run/` = Tier 2 (xem trước production path).

---

## Còn làm gì nữa không?

**Part 3: Xong.** Có thể chuyển sang **Part 4: API Security**.

Tuỳ chọn (không bắt buộc):

- Bookmark public URL để nộp bài
- Thử `/docs` trên Railway URL (Swagger UI)
- Đọc `render.yaml` vs `railway.toml` để so sánh (không cần deploy Render)

---

# Part 4 — Mission Answers: API Security

> Đã hoàn thành và test trên Windows + Python 3.14

---

## Luồng bảo vệ (tổng quan)

```
Request
  → Auth Check        (401/403 nếu fail)
  → Rate Limit        (429 nếu vượt quota)
  → Input Validation  (422 nếu invalid)
  → Cost Check        (402 nếu hết budget)
  → Agent             (200 nếu OK)
```

---

## Exercise 4.1 — API Key Authentication (`develop/`)

### Lệnh đã chạy

```powershell
cd 04-api-gateway\develop
pip install -r requirements.txt
$env:AGENT_API_KEY = "my-secret-key"
$env:PYTHONUTF8 = "1"
python app.py
```

### Câu trả lời đọc code


| Câu hỏi              | Trả lời                                                                       |
| -------------------- | ----------------------------------------------------------------------------- |
| API key check ở đâu? | Dependency `verify_api_key()` — đọc header `**X-API-Key**` qua `APIKeyHeader` |
| Sai key thì sao?     | Thiếu key → **401**; sai key → **403**                                        |
| Rotate key?          | Đổi env var `AGENT_API_KEY` → restart app. Không sửa code, không commit key   |


### Kết quả test


| Test                                   | HTTP    | Chi tiết                                            |
| -------------------------------------- | ------- | --------------------------------------------------- |
| `POST /ask` không có key               | **401** | `"Missing API key. Include header: X-API-Key: ..."` |
| `POST /ask` key sai                    | **403** | `"Invalid API key."`                                |
| `POST /ask` key đúng (`my-secret-key`) | **200** | Trả `question` + `answer`                           |
| `GET /health` (public)                 | **200** | `{"status":"ok"}` — không cần auth                  |


```powershell
# Valid
curl.exe -X POST "http://localhost:8000/ask?question=hello" -H "X-API-Key: my-secret-key"
```

**Lưu ý:** `develop/app.py` dùng query param `?question=`, không phải JSON body.

---

## Exercise 4.2 — JWT Authentication (`production/`)

### Lệnh đã chạy

```powershell
cd ..\production
pip install pyjwt==2.9.0   # + fastapi, uvicorn đã có
$env:PYTHONUTF8 = "1"
python -c "import uvicorn; uvicorn.run('app:app', host='0.0.0.0', port=8000)"
```

### JWT flow (`auth.py`)

```
1. POST /auth/token  {username, password}
   → authenticate_user() check DEMO_USERS
   → create_token() → JWT signed với HS256

2. POST /ask  Header: Authorization: Bearer <token>
   → verify_token() decode JWT
   → extract username, role
   → process request
```

**Demo accounts:**


| Username  | Password   | Role  | Rate limit   |
| --------- | ---------- | ----- | ------------ |
| `student` | `demo123`  | user  | 10 req/phút  |
| `teacher` | `teach456` | admin | 100 req/phút |


### Kết quả test


| Test                         | HTTP    | Chi tiết                                                       |
| ---------------------------- | ------- | -------------------------------------------------------------- |
| `POST /ask` không token      | **401** | `"Authentication required..."`                                 |
| `POST /auth/token` student   | **200** | `access_token`, `token_type: bearer`, `expires_in_minutes: 60` |
| `POST /ask` với Bearer token | **200** | `rate_remaining=9` sau request đầu                             |


```powershell
$login = Invoke-RestMethod -Uri "http://localhost:8000/auth/token" -Method POST `
  -ContentType "application/json" -Body '{"username":"student","password":"demo123"}'
$TOKEN = $login.access_token

Invoke-RestMethod -Uri "http://localhost:8000/ask" -Method POST `
  -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -Body '{"question": "Explain JWT"}'
```

Endpoint token là `**/auth/token**` (không phải `/token` trong CODE_LAB cũ).

---

## Exercise 4.3 — Rate Limiting (`rate_limiter.py`)

### Câu trả lời đọc code


| Câu hỏi                             | Trả lời                                                                                  |
| ----------------------------------- | ---------------------------------------------------------------------------------------- |
| Algorithm nào được dùng?            | **Sliding Window** — `deque` lưu timestamps, loại request cũ hơn 60 giây                 |
| Limit là bao nhiêu requests/minute? | **User: 10 req/60s**; **Admin: 100 req/60s**                                             |
| Làm sao bypass limit cho admin?     | Role `admin` dùng `rate_limiter_admin` (100 vs 10) — limit cao hơn, không miễn hoàn toàn |


### Kết quả test spam 20 requests (user `student`)

```
200 = 9   (1 request trước đó trong cùng window → còn 9 slot)
429 = 11  (vượt limit → Too Many Requests)
```

Response 429 kèm headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`.

### Test admin (`teacher`) — 15 requests

```
Admin succeeded: 15/15   (limit 100/phút — không chạm ngưỡng)
```

---

## Exercise 4.4 — Cost Guard (`cost_guard.py`)

### Implementation trong repo

Code **đã implement sẵn** (in-memory `CostGuard`, không phải Redis TODO):


| Config             | Giá trị                       |
| ------------------ | ----------------------------- |
| Budget/user/ngày   | **$1.00**                     |
| Budget global/ngày | **$10.00**                    |
| Cảnh báo           | 80% budget (`logger.warning`) |
| Vượt budget user   | **402** Payment Required      |
| Vượt budget global | **503** Service Unavailable   |


### Logic chính

```python
# Trước gọi LLM
cost_guard.check_budget(username)

# Sau gọi LLM
cost_guard.record_usage(username, input_tokens, output_tokens)
```

### Kết quả `/me/usage` (sau 10 requests)

```
requests=10
cost_usd=0.000183
budget_remaining_usd=0.999817
budget_used_pct=0.0%
```

### Redis version (CODE_LAB gợi ý — cho production scale)

```python
# Key: budget:{user_id}:{YYYY-MM}
# $10/tháng/user, track trong Redis, reset đầu tháng
```

In-memory OK cho demo 1 instance; scale nhiều instance → cần Redis (Part 5/6).

---

## Fix khi chạy trên Python 3.14

**Lỗi:** `AttributeError: 'MutableHeaders' object has no attribute 'pop'`  
**File:** `production/app.py` middleware `security_headers`  
**Sửa:** `del response.headers["server"]` thay vì `.pop()`

---

## Checkpoint 4 ✅

- Hiểu API Key authentication (`develop/` — 401/403/200)
- Hiểu JWT flow (`/auth/token` → Bearer token)
- Test rate limiting — 429 sau khi vượt 10 req/phút (user)
- Hiểu cost guard — track cost, `/me/usage`, 402 khi hết budget

---

## Câu hỏi thảo luận (README Section 4)

> Nguồn: [README.md](./README.md)

### 1. Khi nào nên dùng API Key vs JWT vs OAuth2?


| Phương thức | Dùng khi                                              | Ví dụ lab                       |
| ----------- | ----------------------------------------------------- | ------------------------------- |
| **API Key** | B2B, internal API, MVP, server-to-server              | `develop/` — header `X-API-Key` |
| **JWT**     | App có user login, mobile/web client, cần role/expiry | `production/` — `/auth/token`   |
| **OAuth2**  | Third-party login (Google, GitHub), enterprise SSO    | Không cover trong lab           |


**Quy tắc chọn:**

- 1 key cho cả team/service → **API Key**
- Nhiều user, mỗi user identity riêng → **JWT**
- User login bằng Google/Facebook → **OAuth2**

API Key đơn giản nhưng không phân biệt user (1 key = 1 client). JWT stateless — server không cần session DB, token chứa `sub`, `role`, `exp`.

---

### 2. Rate limit nên đặt bao nhiêu request/phút cho AI agent?

Phụ thuộc **chi phí LLM**, **latency**, và **use case**:


| User type       | Gợi ý          | Lab                      |
| --------------- | -------------- | ------------------------ |
| Free/anonymous  | 5–10 req/phút  | 10 req/phút (`student`)  |
| Registered user | 20–30 req/phút | —                        |
| Paid tier       | 60+ req/phút   | —                        |
| Admin/internal  | 100+ req/phút  | 100 req/phút (`teacher`) |


**Cách tính thô:**

```
Budget $1/ngày ÷ $0.001/request ≈ 1000 requests/ngày
→ ~0.7 req/phút nếu dùng đều 24h
→ Rate limit 10/phút + cost guard $1/ngày = 2 lớp bảo vệ
```

Lab dùng **cả rate limit (429) và cost guard (402)** — rate limit chặn burst abuse, cost guard chặt tổng chi phí.

---

### 3. Nếu API key bị lộ, phát hiện và xử lý như thế nào?

**Phát hiện:**

- Spike traffic bất thường trong logs/metrics
- Chi phí OpenAI tăng đột biến
- Request từ IP/region lạ
- GitHub secret scanning alert (nếu push nhầm key)
- User báo cáo abuse

**Xử lý ngay (incident response):**

1. **Revoke key** — đổi `AGENT_API_KEY` trên Railway/dashboard → redeploy
2. **Audit** — xem logs: IP, endpoints, thời gian abuse
3. **Thông báo** — nếu key liên quan billing thật (OpenAI)
4. **Rotate** — tạo key mới, cập nhật clients hợp lệ
5. **Post-mortem** — tại sao lộ? (commit Git, log console, share URL có key)

**Phòng ngừa:**

- Key chỉ trong env var / Secret Manager — never in code
- Rate limit + cost guard (như Part 4)
- `.gitignore` `.env`, `.dockerignore` secrets
- Rotate key định kỳ (90 ngày)
- Separate keys per environment (dev/staging/prod)

**Áp dụng lên Railway (Part 3):**

```powershell
railway variables set AGENT_API_KEY=new-rotated-key
railway up   # redeploy
```

---

## Tóm tắt so sánh develop vs production


|            | `develop/`            | `production/`                 |
| ---------- | --------------------- | ----------------------------- |
| Auth       | API Key (`X-API-Key`) | JWT (`Authorization: Bearer`) |
| Rate limit | Không                 | 10/100 req/phút               |
| Cost guard | Không                 | $1/user/ngày                  |
| Phù hợp    | MVP, internal         | Production-facing API         |


**Part 4 hoàn thành.** Tiếp theo: **Part 5 — Scaling & Reliability**.

---

# Part 5 — Mission Answers: Scaling & Reliability

---

## Concepts

**Vấn đề:** 1 instance không đủ khi có nhiều users.

**Giải pháp:**


| Concept               | Mục đích                                                   |
| --------------------- | ---------------------------------------------------------- |
| **Stateless**         | State trong Redis, không trong RAM — mọi instance đọc được |
| **Health checks**     | Platform biết khi restart (`/health`, `/ready`)            |
| **Graceful shutdown** | Hoàn thành request trước khi tắt                           |
| **Load balancing**    | Nginx phân tán traffic qua nhiều agent                     |


---

## Exercise 5.1 — Health checks (`develop/`)

### Code đã có sẵn trong `develop/app.py`


| Endpoint      | Loại          | Khi nào dùng                                |
| ------------- | ------------- | ------------------------------------------- |
| `GET /health` | **Liveness**  | Process còn sống? Platform restart nếu fail |
| `GET /ready`  | **Readiness** | Sẵn sàng nhận traffic? LB route nếu 200     |


### Lệnh đã chạy

```powershell
cd 05-scaling-reliability\develop
pip install -r requirements.txt
$env:PYTHONUTF8 = "1"
python app.py
```

### Kết quả test


| Endpoint                   | HTTP | Response                                        |
| -------------------------- | ---- | ----------------------------------------------- |
| `GET /health`              | 200  | `status: ok`, `uptime_seconds`, `checks.memory` |
| `GET /ready`               | 200  | `ready: true`, `in_flight_requests`             |
| `POST /ask?question=hello` | 200  | Mock LLM answer                                 |


```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/ready
```

**Khác biệt:**

- `/health` — luôn 200 nếu process chạy (kể cả đang startup)
- `/ready` — **503** khi `_is_ready=False` (startup/shutdown)

---

## Exercise 5.2 — Graceful shutdown (`develop/`)

### Code đã có sẵn

1. `**lifespan` context manager** — startup set `_is_ready=True`, shutdown chờ in-flight requests
2. **Middleware `track_requests`** — đếm `_in_flight_requests`
3. `**handle_sigterm**` — log khi nhận SIGTERM; uvicorn gọi lifespan shutdown
4. `**timeout_graceful_shutdown=30**` — chờ tối đa 30s

```python
# Shutdown flow trong lifespan:
_is_ready = False
while _in_flight_requests > 0 and elapsed < 30:
    wait...
logger.info("✅ Shutdown complete")
```

### Test trên Windows

Linux: `kill -TERM $PID`  
Windows: `Ctrl+C` hoặc Stop-Process — uvicorn bắt SIGINT tương tự.

**Quan sát khi tắt:** Log hiện `Graceful shutdown initiated...` → chờ in-flight → `Shutdown complete`.

---

## Exercise 5.3 — Stateless design (`production/app.py`)

### Anti-pattern vs Correct

```python
# ❌ Anti-pattern — mỗi instance RAM riêng
conversation_history = {}

# ✅ Correct — Redis shared
def load_session(session_id):
    return json.loads(_redis.get(f"session:{session_id}"))
```

### Implementation trong repo


| Function              | Làm gì                                         |
| --------------------- | ---------------------------------------------- |
| `save_session()`      | Lưu JSON vào Redis key `session:{id}` + TTL 1h |
| `load_session()`      | Đọc session từ Redis                           |
| `append_to_history()` | Thêm message user/assistant vào history        |


**Fallback:** Nếu Redis không có → in-memory (demo only, **không scale**).

Response field `**served_by: instance-xxxxx`** — chứng minh request qua instance khác nhau.

---

## Exercise 5.4 — Load balancing (Docker Compose)

### Files đã thêm (repo thiếu — cần để chạy compose)


| File                          | Mục đích                          |
| ----------------------------- | --------------------------------- |
| `production/Dockerfile`       | Build agent image                 |
| `production/requirements.txt` | fastapi, uvicorn, redis, pydantic |
| `production/.env.local`       | Env cho compose                   |


### Architecture

```
Client :8080
    ↓
  Nginx (round-robin)
    ↓
┌─────────┬─────────┬─────────┐
│ agent-1 │ agent-2 │ agent-3 │
└────┬────┴────┬────┴────┬────┘
     └─────────┴─────────┘
              ↓
           Redis (shared session)
```

### Lệnh đã chạy

```powershell
cd 05-scaling-reliability\production
docker compose up -d --build --scale agent=3
docker compose ps
```

### Services


| Service | Count           | Port           |
| ------- | --------------- | -------------- |
| agent   | **3 instances** | internal :8000 |
| redis   | 1               | internal :6379 |
| nginx   | 1               | **8080** → 80  |


### Test 10 requests — load balancing

```
Req 1  -> instance-96ed01
Req 2  -> instance-647d3d
Req 3  -> instance-9fe4c4
Req 4  -> instance-96ed01   ← round-robin lặp lại
Req 5  -> instance-647d3d
...
Req 10 -> instance-96ed01
```

**3 instances luân phiên** — Nginx upstream `agent:8000` resolve DNS Docker → tất cả agent containers.

```powershell
curl.exe http://localhost:8080/health
# storage: redis, redis_connected: true
```

---

## Exercise 5.5 — Test stateless (`test_stateless.py`)

### Lệnh

```powershell
cd 05-scaling-reliability\production
$env:PYTHONUTF8 = "1"
python test_stateless.py
```

### Kết quả

```
Session ID: 4929ee58-7b3a-494a-8677-6c608f5432ac

Request 1: [instance-96ed01]  What is Docker?
Request 2: [instance-647d3d]  Why do we need containers?
Request 3: [instance-9fe4c4]  What is Kubernetes?
Request 4: [instance-96ed01]  How does load balancing work?
Request 5: [instance-647d3d]  What is Redis used for?

Instances used: {instance-96ed01, instance-647d3d, instance-9fe4c4}
✅ All requests served despite different instances!

Conversation History: 10 messages (5 user + 5 assistant)
✅ Session history preserved across all instances via Redis!
```

**Chứng minh stateless:** Cùng `session_id`, requests qua **3 instance khác nhau**, history **vẫn đầy đủ** vì state trong Redis.

---

## Checkpoint 5 ✅

- Health và readiness checks (`/health`, `/ready`)
- Graceful shutdown (lifespan + in-flight tracking)
- Stateless design (session trong Redis)
- Load balancing với Nginx (3 instances, round-robin)
- `test_stateless.py` pass

---

## Câu hỏi tổng hợp (từ CODE_LAB concepts)

### 1. Tại sao stateless quan trọng khi scale?

```
User → Load Balancer → [Agent 1] [Agent 2] [Agent 3]
                            ↓
              conversation_history = {}  ← RAM riêng mỗi instance
```

Request 1 → Agent 1 (lưu history RAM)  
Request 2 → Agent 2 (không có history) → **BUG**

**Giải pháp:** Redis — tất cả instance đọc/ghi cùng `session:{id}`.

Lab chứng minh: 5 requests, 3 instances, **10 messages history intact**.

---

### 2. `/health` vs `/ready` khác nhau thế nào?


|             | `/health` (liveness) | `/ready` (readiness)        |
| ----------- | -------------------- | --------------------------- |
| Câu hỏi     | Process còn sống?    | Sẵn sàng nhận traffic?      |
| Fail →      | Restart container    | Ngừng route traffic         |
| Khi startup | Thường vẫn 200       | **503** cho đến khi deps OK |
| Check deps  | Optional (memory)    | Redis ping (production)     |


---

### 3. Graceful shutdown tại sao quan trọng?

Khi deploy mới hoặc scale down, platform gửi **SIGTERM**:

- **Không graceful:** Cắt request đang xử lý → user nhận lỗi giữa chừng
- **Graceful:** Ngừng nhận request mới → hoàn thành in-flight → đóng connections

Railway/K8s rolling deploy **cần** graceful shutdown.

---

## Dừng stack

```powershell
cd 05-scaling-reliability\production
docker compose down
```

---

## Tóm tắt Part 1 → 5


| Part | Concept                                 |
| ---- | --------------------------------------- |
| 1    | Config, health, graceful shutdown       |
| 2    | Docker, multi-stage, compose            |
| 3    | Cloud deploy (Railway)                  |
| 4    | Auth, rate limit, cost guard            |
| 5    | **Scale 3 instances + Redis stateless** |


**Tiếp theo:** Part 6 — Final Project (gộp tất cả).