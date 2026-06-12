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

