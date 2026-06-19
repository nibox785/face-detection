# System Design

Nguyên tắc kiến trúc, phân lớp hiện tại/mục tiêu, và quy tắc phụ thuộc.

**Chi tiết runtime:** `backend.md`, `frontend.md`  
**AI pipeline & abstraction:** `06-ai-pipeline.md`  
**Dependency & coupling:** `dependency-analysis.md`  
**Phase refactor:** `07-implementation.md`

## Design Principles

### Separation of Concerns

Trách nhiệm tách thành các layer độc lập — mỗi layer chỉ giao tiếp với layer liền kề:

API → Application Services → Domain Pipelines → Repositories → Infrastructure → AI Engine

### Single Responsibility

Mỗi component một năng lực nghiệp vụ: Auth, Registration, Recognition, Attendance, WebSocket.

### AI Pipeline Isolation

Thay RetinaFace → YOLOv11-face, FaceNet512 → ArcFace **không được** ảnh hưởng API contract hay business services. Chi tiết: `06-ai-pipeline.md`.

### Dependency Inversion

Business logic không phụ thuộc trực tiếp SQLite, FAISS, RetinaFace, FaceNet — tương tác qua repositories và engine abstractions.

### Extensibility

Detector, Recognizer, Search Engine, Liveness thay thế qua interfaces + config (`DETECTOR`, `RECOGNIZER`).

## Mục tiêu thiết kế

- Tách trách nhiệm theo lớp, tối thiểu phụ thuộc chéo.
- Quản lý tập trung tài nguyên nặng (model, FAISS, DB).
- Interface AI nhỏ, rõ — thay implementation an toàn.
- Refactor incremental, testable, rollbackable.

## Vấn đề kiến trúc hiện tại

- `FaceService` gom detect, embedding, liveness, search, recognize.
- FAISS global trong `main.py`; `common.py` / `recognize_routes.py` import ngược.
- `*_routes.py` vẫn gọi trực tiếp `db.py`.
- `face_engine/facenet/*` gắn chặt DeepFace.
- **Đã cải thiện:** domain routers + `routes.py` aggregator (Phase A).

Chi tiết: `dependency-analysis.md`.

## Quy tắc phụ thuộc

1. Nghiệp vụ → `RecognitionPipeline` → Primitive AI → Hạ tầng.
2. Implementation inject qua interface/factory.
3. AI và hạ tầng không import logic nghiệp vụ.
4. Logging, config là cross-cutting — không chứa business rules.

**Cho phép:** đổi detector/recognizer bằng config; services gọi pipeline; telemetry/benchmark theo bước.

**Cấm:** route gọi DB trực tiếp (mục tiêu); AI chứa business rules; khởi tạo model/index phân tán; đổi contract không kèm test hồi quy.

## Kiến trúc

### Hiện tại

```
Client → FastAPI → FaceService → RetinaFace → FaceNet512 → FAISS → SQLite
```

Module map runtime: `backend.md`.

### Mục tiêu

```
Frontend → API Layer → Application Services → Domain Pipelines
         → Repositories → Infrastructure → AI Engine
```

```
            +--------------------+
            |   Lớp API          |
            +---------+----------+
                      v
            +--------------------+
            |  Lớp Nghiệp Vụ     |
            +---------+----------+
                      v
      +---------------+-----------------+
      |  RecognitionPipeline (lõi)    |
      |  Detect → Embed → Liveness →  |
      |  Search → Decision            |
      +---------------+-----------------+
                      v
        +-------------+-------------+
        | Lớp AI  |  Lớp Hạ tầng   |
        +---------------------------+
```

`RecognitionPipeline` là entry point duy nhất cho xử lý ảnh — thứ tự bước nhất quán, telemetry theo từng bước.

## Phân lớp

| Layer | Location (hiện tại / mục tiêu) | Trách nhiệm |
|-------|-------------------------------|-------------|
| Frontend | `frontend/src/` | Camera, UI, auth, dashboard — `frontend.md` |
| API | `backend/api/*_routes.py`, `common.py` | Validate, auth, gọi service, trả response |
| Services | `backend/services/` | Business rules; mục tiêu tách Auth/Registration/Recognition/Attendance/WebSocket |
| Domain | `face_engine/pipeline/` (mục tiêu) | `RegistrationPipeline`, `RecognitionPipeline`, `DecisionEngine` |
| Repositories | `backend/repositories/` (mục tiêu) | Student, Embedding, Attendance, Token persistence |
| Infrastructure | SQLite, FAISS, `dataset/`, cache | `09-database-design.md` |
| AI Engine | `face_engine/` | Detector, Recognizer, Liveness — `06-ai-pipeline.md` |

### Domain pipelines (mục tiêu)

- **RegistrationPipeline** — decode → detect → quality scoring → embed → chọn frame tốt nhất.
- **RecognitionPipeline** — detect → embed → liveness → search → normalize.
- **DecisionEngine** — score → `AUTO_MARK` / `MANUAL_REVIEW` / `REJECT` (ngưỡng: `08-api-design.md`).

### Repositories (mục tiêu)

| Repository | Methods chính |
|------------|---------------|
| StudentRepository | `get_by_id`, `get_by_mssv`, `create`, `update` |
| EmbeddingRepository | `save`, `save_many`, `get_all` |
| AttendanceRepository | `create`, `get_today`, `get_by_student` |
| TokenRepository | `revoke`, `is_revoked` |

## Luồng runtime

Quy tắc nghiệp vụ: `02-user-requirements.md`. Luồng chi tiết (register, recognize, WebSocket, startup): `backend.md`.

**Hiện tại (tóm tắt):** Client → Route → Service → FaceService (AI) → FAISS/DB → Response.

**Mục tiêu:** Client → API → `RecognitionPipeline` → Decision → Attendance → Repository → Response.

## Security

- JWT Bearer; revoke qua `revoked_tokens` (`08-api-design.md`).
- Rate limiting (slowapi), input/file validation, anti-spoof.

## Folder structure (mục tiêu)

```
core/config.py
face_engine/{detector, recognizer, liveness, pipeline/}
backend/{api, services, database, repositories/}
```

## Refactor phases

| Phase | Trạng thái | Nội dung |
|-------|------------|----------|
| A | **Xong** | Domain routers + `common.py` |
| 1–7 | Xem `07-implementation.md` | Pipeline, config, detector, YOLO, ArcFace, ByteTrack, test/benchmark |

## Tiêu chí thành công

- API contract giữ nguyên từ góc client (`08-api-design.md`).
- Telemetry latency/lỗi theo bước pipeline.
- Đổi detector/recognizer bằng config + test tự động.
- Không còn route gọi DB trực tiếp.
- Latency end-to-end không chậm hơn baseline >20%.

## Cross-cutting

| Concern | Reference |
|---------|-----------|
| Config | `core/config.py`, `04-tech-solutions.md` |
| Testing | `10-testing.md` |
| Benchmark | `11-benchmark.md` |
| Health | `GET /health`, `GET /debug/faiss-info` |

## Lộ trình công nghệ

| Thành phần | Hiện tại | Mục tiêu |
|------------|----------|----------|
| Detector | RetinaFace | YOLOv11-face |
| Recognizer | FaceNet512 | ArcFace |
| Tracking | OpenCV | ByteTrack |
| FAISS | IndexFlatL2 | IndexFlatIP (embedding normalized) |

## Future extensions

Multi-camera, classroom management, model versioning, cloud deployment, distributed FAISS, audit logging.
