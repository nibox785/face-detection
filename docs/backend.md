# Backend Documentation

# Request Lifecycle

## Recognition Request

Client
↓
POST /recognize
↓
Recognition Service
↓
Face Detection
↓
Embedding Extraction
↓
FAISS Search
↓
Attendance Validation
↓
Database Update
↓
Response

---

## Registration Request

Client
↓
POST /register
↓
Register Service
↓
Face Detection
↓
Embedding Extraction
↓
FAISS Index Update
↓
Database Insert
↓
Response

# Future Refactor

Current:

FaceService

Target:

RecognitionPipeline
├── Detector
├── Recognizer
├── Search
└── Decision Engine

## 1) Tong quan backend

Backend dung FastAPI va chia thanh cac layer ro rang:

- `api/routes.py`: khai bao endpoint va auth gate.
- `services/`: business logic (register, attendance, face service, FAISS).
- `database/db.py`: SQLite CRUD + migration nhe + index.
- `database/schemas.py`: response model Pydantic.
- `main.py`: khoi tao app, CORS, lifespan, warm-up model.

Ghi chu: de dung WebSocket endpoint (`/api/ws/...`), can cai `uvicorn[standard]` (hoac tuong duong `websockets`/`wsproto`).

Muc tieu: de bao tri, de benchmark, de thay the/tinh chinh model trong tuong lai.

## 2) Lifespan va startup

Khi app khoi dong (`backend/main.py`):

1. `init_db()` tao/migrate schema SQLite.
2. `update_embeddings_cache()` nap embedding cache tu DB.
3. `init_faiss_index()` build FAISS index tu cache.
4. `warmup_ai_models()` (co the tat bang `MODEL_WARMUP_ENABLED=0`) de giam cold-start.

Endpoint debug:
- `GET /debug/faiss-info`
- `GET /health`

## 3) Auth va bao mat

- JWT dung `HS256` voi `SECRET_KEY` (`core/config.py`).
- Token co `exp` va `jti`.
- Logout revoke `jti` vao bang `revoked_tokens` (khong con blacklist RAM).
- Kiem tra token:
  - `POST /api/login`
  - `POST /api/logout`
  - `GET /api/auth/verify`
- `/api/recognize` bat buoc co `Authorization: Bearer <token>`.

## 4) API hien tai (`/api`)

### Auth
- `POST /login`
- `POST /logout`
- `GET /auth/verify`

### Register / Face utility
- `POST /register` (single image)
- `POST /dataset/register` (single image + luu dataset)
- `POST /dataset/register-multiple` (10 images + quality scoring)
- `POST /face/check`
- `POST /face/liveness-check`

### Recognize
- `POST /recognize`

### WebSocket realtime

- `GET /api/ws/recognize?token=...`
  - Mode cu: FE gui full frame (base64) + `track_hints[]`, backend detect face va co gang gan `track_id` theo hint.
- `GET /api/ws/realtime/{session_id}?token=...`
  - Mode B (server-side tracking): FE gui full frame, backend detect + gan `track_id` + tra `bbox + result` de FE ve overlay lien tuc.

#### Contract `/api/ws/realtime/{session_id}`

- Client -> server:
  - `{"type":"ping"}`
  - `{"type":"frame","frame_id":"...","image":"data:image/jpeg;base64,..."}`
- Server -> client:
  - `{"type":"pong","ts": 171...}`
  - `{"type":"frame_result","session_id":"...","frame_id":"...","tracks":[{"track_id":"...","bbox":{...},"result":{...}}]}`
  - `{"type":"error","message":"...","frame_id":"..." }`

### Student / Attendance management
- `GET /students`
- `GET /students/{student_id}`
- `PUT /students/{student_id}` (nhan `name` qua form-data)
- `DELETE /students/{student_id}`
- `GET /attendance`
- `GET /attendance/export`

## 5) Face pipeline

Pipeline trong `routes.py` + `services/face_service.py`:

1. Detect face (`face_engine/facenet/detect.py`): DeepFace.extract_faces voi `detector_backend="retinaface"`.
2. Embedding (`face_engine/facenet/embedding.py`): DeepFace.represent model `Facenet512`.
3. Liveness gate (`get_embedding_with_liveness`).
4. Similarity search:
   - uu tien FAISS index (neu available),
   - fallback loop cosine similarity.
5. Tra ve top-3 candidates + decision:
   - `AUTO_MARK` neu score >= 0.72,
   - `MANUAL_REVIEW` neu score >= 0.55,
   - nguoc lai `REJECT`.

## 6) Dang ky nhieu anh

`POST /dataset/register-multiple` su dung quy trinh:

- Nhan toi thieu 10 anh (`TARGET_REGISTRATION_FRAMES=10`).
- Moi frame duoc tinh quality score (do net, do sang, ti le khuon mat, vi tri tam, confidence).
- Chon frame dat chat luong, fallback neu can.
- Yeu cau it nhat 4 frame dat (`MIN_ACCEPTED_REGISTRATION_FRAMES=4`).
- Luu embedding + luu anh vao `dataset/` + cap nhat cache FAISS.

## 7) Database interaction

Tat ca thao tac DB di qua `backend/database/db.py`:

- Student CRUD + MSSV unique check.
- Embedding serialize dang binary (`EMB1 + float32 bytes`).
- Backward compatibility voi blob cu (pickle).
- Attendance insert/check theo ngay (UTC+7).
- Revoke token va cleanup token het han.

## 8) FAISS va benchmark

- FAISS index class: `backend/services/faiss_search.py`.
- Benchmark files:
  - `tests/benchmark_faiss.py`
  - `scripts/benchmark_recognize_latency.py`
  - `scripts/benchmark_threshold.py`

Ket qua benchmark duoc ghi vao thu muc `benchmarks/`.

## 9) Ghi chu han che hien tai

- `PUT /students/{student_id}` dang nhan form-data, can giu dong bo payload giua frontend va backend.
- Rate limiting chi bat khi cai `slowapi`.
- Chua co pagination cho danh sach lon.

