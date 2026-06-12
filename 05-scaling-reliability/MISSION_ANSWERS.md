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