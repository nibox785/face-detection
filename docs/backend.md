# Backend Runtime

Tài liệu mô tả cách backend **đang chạy** thực tế. Kiến trúc mục tiêu: `05-system-design.md`. API contract: `08-api-design.md`. Database: `09-database-design.md`. AI pipeline: `06-ai-pipeline.md`.

## Module map

```
backend/
  main.py              # FastAPI app, CORS, lifespan, /health, /debug/faiss-info
  api/
    routes.py          # aggregator (re-export)
    auth_routes.py
    register_routes.py
    recognize_routes.py
    attendance_routes.py
    websocket_routes.py
    common.py          # cache, FAISS helpers, thresholds, image/WS utils
  services/
    face_service.py
    register_service.py
    attendance_service.py
    faiss_search.py
  database/
    db.py
    schemas.py
```

Router HTTP/WebSocket được mount tại prefix `/api` trong `main.py`. WebSocket URL đầy đủ: `/api/ws/...`.

**Triển khai:** cần `uvicorn[standard]` (hoặc `websockets` / `wsproto`) để dùng WebSocket.

## Startup (`backend/main.py`)

1. `init_db()`
2. `update_embeddings_cache()`
3. `init_faiss_index()`
4. `warmup_ai_models()` — tắt bằng `MODEL_WARMUP_ENABLED=0`

Debug: `GET /health`, `GET /debug/faiss-info`

## Runtime flows

Quy tắc nghiệp vụ: `02-user-requirements.md`.

| Luồng | Đường đi |
|-------|----------|
| Đăng ký | `POST /api/dataset/register-multiple` → `RegisterService` → quality + detect + embed → DB + FAISS |
| Nhận diện ảnh | `POST /api/recognize` → `FaceService` → liveness + FAISS → decision → `AttendanceService` |
| Realtime | WebSocket Mode A/B → tracking + cooldown → `FaceService` → response |
| Điểm danh | Recognition result → `AttendanceService` → kiểm tra trùng ngày → ghi DB |

## Auth runtime

- JWT `HS256`, `SECRET_KEY` từ `core/config.py`.
- Payload có `exp` và `jti`; logout ghi `jti` vào bảng `revoked_tokens`.
- Endpoint bảo vệ yêu cầu `Authorization: Bearer <token>` (ví dụ `POST /api/recognize`).

## WebSocket modes

| Endpoint | Mục đích |
|----------|----------|
| `GET /api/ws/recognize?token=...` | Mode A — client gửi frame + `track_hints[]`; server detect và gắn `track_id` theo hint |
| `GET /api/ws/realtime/{session_id}?token=...` | Mode B — server-side tracking; trả `bbox + result` liên tục cho overlay |

Message contract chi tiết: `08-api-design.md` §WebSocket.

Frontend build URL qua `apiClient.js` (`getWsOrigin()` → `ws://host:8000/api`).

## Face pipeline (runtime)

Luồng trong `recognize_routes.py` + `services/face_service.py`:

1. Detect — `face_engine/facenet/detect.py` (RetinaFace qua DeepFace).
2. Embed — `face_engine/facenet/embedding.py` (FaceNet512).
3. Liveness — `get_embedding_with_liveness`.
4. Search — FAISS ưu tiên, fallback cosine loop.
5. Decision + top-3 candidates — ngưỡng trong `backend/api/common.py` (xem `08-api-design.md` §Decision thresholds).

## Đăng ký nhiều ảnh

`POST /api/dataset/register-multiple` (`register_routes.py`):

- Yêu cầu tối thiểu **10** ảnh (`TARGET_REGISTRATION_FRAMES=10`).
- Mỗi frame được chấm quality (độ nét, sáng, tỷ lệ mặt, vị trí, confidence).
- Cần ít nhất **4** frame đạt (`MIN_ACCEPTED_REGISTRATION_FRAMES=4`).
- Lưu embedding, ảnh vào `dataset/`, cập nhật embedding cache và FAISS.

## Hạn chế hiện tại

- `PUT /api/students/{student_id}` chỉ nhận `name` qua `multipart/form-data` — chưa hỗ trợ cập nhật `mssv` qua endpoint này.
- Rate limiting chỉ bật khi cài `slowapi`.
- Chưa có pagination cho danh sách lớn.
- `FaceService` vẫn gom nhiều trách nhiệm AI — mục tiêu tách sang `RecognitionPipeline` (xem `05-system-design.md`).
