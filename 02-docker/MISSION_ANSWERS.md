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

