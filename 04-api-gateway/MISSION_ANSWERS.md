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