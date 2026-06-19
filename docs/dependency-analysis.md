# Dependency Analysis

Phân tích phụ thuộc codebase **hiện tại** (sau khi tách domain routers). Kiến trúc mục tiêu: `05-system-design.md`.

## Mục tiêu

Làm rõ coupling, dependency hotspots, và hướng refactor tiếp theo sau Phase A (route separation).

## Dependency overview

### 1. Backend entrypoint

- `backend/main.py`
  - FastAPI app, CORS, lifespan.
  - `init_db()` → `backend/database/db.py`.
  - `update_embeddings_cache()` → `backend/api/common.py`.
  - `init_faiss_index()` — global `faiss_index` (`FAISSEmbeddingIndex`).
  - `warmup_ai_models()` → `face_engine/facenet`.
  - Mount `router` từ `backend/api/routes.py` tại prefix `/api`.
  - Endpoints root: `/`, `/health`, `/debug/faiss-info`.

### 2. API layer

- `backend/api/routes.py` — aggregator, re-export `router` và `common` helpers.
- `backend/api/__init__.py` — ghép domain routers:
  - `auth_routes.py`
  - `register_routes.py`
  - `recognize_routes.py`
  - `attendance_routes.py`
  - `websocket_routes.py`
- `backend/api/common.py`
  - `embeddings_cache`, `update_embeddings_cache()`.
  - Thresholds đăng ký / decision.
  - Image/WS helpers, rate limiter.
  - Import `get_all_embeddings` từ `db.py`.
  - Dynamic import `backend.main` (`init_faiss_index`, `faiss_index`) khi rebuild/incremental FAISS.

| File route | Phụ thuộc chính |
|------------|-----------------|
| `auth_routes.py` | `db.py` (revoke token), `core/config.py`, JWT |
| `register_routes.py` | `register_service`, `face_service`, `db.py` (student/embedding CRUD), `common.py` |
| `recognize_routes.py` | `face_service`, `attendance_service`, `db.py`, `common.py`, `backend.main.faiss_index` |
| `attendance_routes.py` | `db.py` (students, attendance), `schemas.py` |
| `websocket_routes.py` | `recognize_routes` helpers, `face_service`, `db.py`, `common.py` |

### 3. Service layer

- `backend/services/face_service.py` — detect, embed, liveness, similarity, top-k → `face_engine/facenet/*`.
- `backend/services/register_service.py` — → `face_service`, `db.py`, OpenCV.
- `backend/services/attendance_service.py` — → `db.py`.
- `backend/services/faiss_search.py` — FAISS index class; nhận data từ cache, không đọc DB trực tiếp.

### 4. Database layer

- `backend/database/db.py` — schema, CRUD, migration nhẹ.
- `backend/database/schemas.py` — Pydantic request/response.

### 5. AI engine layer

- `face_engine/facenet/detect.py` — DeepFace RetinaFace.
- `face_engine/facenet/embedding.py` — FaceNet512, liveness.

## Dependency graph

```text
frontend <-- HTTP/WebSocket --> backend/api/__init__.py (router)
  |-- auth_routes.py ----------> backend/database/db.py
  |-- register_routes.py -----> register_service, face_service, db.py, common.py
  |-- recognize_routes.py ----> face_service, attendance_service, db.py, common.py
  |                              \-> backend.main.faiss_index (dynamic)
  |-- attendance_routes.py ---> db.py
  |-- websocket_routes.py ----> recognize helpers, face_service, db.py, common.py
  \-- common.py --------------> db.py, backend.main (dynamic)

backend/services/register_service.py --> face_service.py, db.py
backend/services/attendance_service.py --> db.py
backend/services/face_service.py --> face_engine/facenet/{detect,embedding}

backend/main.py --> db.py, routes.py, faiss_search.py, common.py, face_engine (warmup)
```

## Dependency diagram (ASCII)

```text
frontend
  |
  | HTTP / WebSocket (/api/...)
  v
backend/api/__init__.py
  |
  +-- auth_routes.py --> db.py, core/config.py
  |
  +-- register_routes.py --> register_service --> face_service --> face_engine
  |                        \-> db.py, common.py
  |
  +-- recognize_routes.py --> face_service, attendance_service --> db.py
  |                           \-> common.py --> main.faiss_index (dynamic)
  |
  +-- attendance_routes.py --> db.py
  |
  +-- websocket_routes.py --> recognize helpers, face_service, db.py
  |
  +-- common.py --> db.py, main.{faiss_index, init_faiss_index}

backend/main.py
  |-- init_db() --> db.py
  |-- update_embeddings_cache() --> common.py
  |-- init_faiss_index() --> faiss_search.py + embeddings_cache
  \-- include_router(routes) --> api/__init__.py
```

## Tiến độ refactor (Phase A)

**Đã xong**

- Tách `routes.py` monolith thành domain routers + `common.py`.
- `routes.py` chỉ còn aggregator.

**Chưa xong**

- Route vẫn gọi `db.py` trực tiếp (`attendance_routes`, `register_routes`, `auth_routes`).
- FAISS global vẫn sống trong `main.py`; `common.py` / `recognize_routes.py` import ngược.
- `FaceService` vẫn gom nhiều trách nhiệm AI.
- Chưa có `RecognitionPipeline`, repository layer.

## Key coupling issues

### A. Route layer vẫn phụ thuộc DB

`attendance_routes.py`, `register_routes.py`, `auth_routes.py` import trực tiếp nhiều hàm từ `db.py`.

- Ảnh hưởng: handler vẫn chứa logic truy cập dữ liệu.
- Hướng xử lý: `StudentService`, `EnrollmentService`, repository layer.

### B. FaceService làm quá nhiều việc

Detect, embed, liveness, top-k, recognize trong một service.

- Hướng xử lý: `RecognitionPipeline` + `BaseDetector` / `BaseRecognizer` / `LivenessEngine`.

### C. Dynamic import `backend.main`

`common.py` (`init_faiss_index`, `faiss_index`) và `recognize_routes.py` (`faiss_index`) import từ `main`.

- Ảnh hưởng: khó test, dependency loop tiềm ẩn.
- Hướng xử lý: `FaissService` singleton hoặc `app.state`, inject vào routes.

### D. RegisterService → FaceService

Dependency hợp lý nhưng `FaceService` quá lớn kéo theo coupling cho đăng ký.

### E. DeepFace lock-in

`face_engine/facenet/*` gắn chặt RetinaFace / FaceNet512.

## Critical dependency hotspots

| File | Lý do |
|------|-------|
| `backend/api/common.py` | Cache, FAISS bridge, thresholds, import `main` |
| `backend/api/register_routes.py` | Đăng ký + DB + cache update |
| `backend/api/recognize_routes.py` | Recognition flow + FAISS + attendance |
| `backend/services/face_service.py` | AI + business logic mix |
| `backend/main.py` | Startup orchestration + global FAISS |

## Suggested improvements

1. **Route → service/repository** — loại bỏ `db.py` import từ `*_routes.py`.
2. **Tách FaceService** — pipeline + detector/recognizer/liveness/search modules.
3. **FaissService** — quản lý index tập trung, bỏ import `main` trong routes/common.
4. **Config** — `DETECTOR`, `RECOGNIZER`, `USE_FAISS` trong `core/config.py`.
5. **Shared state** — dùng `app.state` hoặc DI thay vì global trong `main`.

## Practical refactor opportunities

| Problem | Hiện tại | Đề xuất |
|---------|----------|---------|
| Route gọi DB trực tiếp | `*_routes.py` → `db.py` | `StudentService`, repositories |
| FaceService monolith | `register_service` → `face_service` | `RecognitionPipeline` |
| FAISS trong `main` | `main` ↔ `common` / `recognize_routes` | `FaissService` / `app.state` |
| DeepFace lock-in | `face_service` → `face_engine/facenet` | `BaseDetector`, `BaseRecognizer` |

## Summary

Phase A đã giảm kích thước API monolith, nhưng coupling cốt lõi vẫn còn:

- DB access từ handlers.
- FAISS global + import ngược từ `main`.
- AI logic chưa tách khỏi `FaceService`.

Ưu tiên tiếp theo (Phase 1–2): `RecognitionPipeline`, `FaissService`, repository layer — theo `05-system-design.md` và `roadmap.md`.
