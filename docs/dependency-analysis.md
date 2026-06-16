# Dependency Analysis

## Mục tiêu

Tài liệu này phân tích các phụ thuộc chính trong hệ thống hiện tại để giúp hiểu rõ coupling, điểm nóng cần refactor, và các luồng dữ liệu quan trọng.

## Dependency overview

### 1. Backend entrypoint

- `backend/main.py`
  - Khởi tạo FastAPI app.
  - Gọi `init_db()` từ `backend/database/db.py`.
  - Nhúng router từ `backend/api/routes.py`.
  - Tạo FAISS index bằng `backend/services/faiss_search.py`.
  - Warmup AI models bằng `face_engine/facenet`.

### 2. API layer

- `backend/api/routes.py`
  - Chịu trách nhiệm định nghĩa endpoint.
  - Khởi tạo các service:
    - `FaceService`
    - `AttendanceService`
    - `RegisterService`
  - Import trực tiếp nhiều hàm từ `backend/database/db.py`.
  - Import cấu hình từ `core/config.py`.
  - Định nghĩa cache `embeddings_cache`, update cache và tái tạo FAISS index.
  - Sử dụng dynamic import `from backend.main import faiss_index` khi cần.

### 3. Service layer

- `backend/services/face_service.py`
  - Detect, embed, liveness, similarity, top-k.
  - Lazy import `face_engine/facenet/detect.py` và `face_engine/facenet/embedding.py`.
  - Phụ thuộc trực tiếp vào `face_engine` và `numpy`.

- `backend/services/register_service.py`
  - Phụ thuộc vào `backend.services.face_service.FaceService`.
  - Phụ thuộc vào `backend.database.db` để tạo student, truy vấn tồn tại, lưu embedding.
  - Kết hợp xử lý ảnh OpenCV với business logic đăng ký.

- `backend/services/attendance_service.py`
  - Phụ thuộc vào `backend.database.db` để kiểm tra và ghi attendance.

- `backend/services/faiss_search.py`
  - Quản lý FAISS index.
  - Không phụ thuộc trực tiếp vào database; nhận dữ liệu từ API/service.

### 4. Database layer

- `backend/database/db.py`
  - Khởi tạo schema SQLite.
  - Cung cấp CRUD cho students, embeddings, attendance, revoked_tokens.
  - Xuất các hàm dùng bởi services và routes.

- `backend/database/schemas.py`
  - Định nghĩa Pydantic models cho API response/request.

### 5. AI engine layer

- `face_engine/facenet/detect.py`
  - Dùng DeepFace RetinaFace để detect mặt.

- `face_engine/facenet/embedding.py`
  - Dùng DeepFace FaceNet512 để represent embedding.
  - Chứa hàm liveness nếu có.

## Dependency graph

```text
frontend <-- HTTP/WebSocket --> backend/api/routes.py
backend/api/routes.py --> backend/services/{face_service,register_service,attendance_service}
backend/api/routes.py --> backend/database/db.py
backend/api/routes.py --> core/config.py
backend/services/register_service.py --> backend/services/face_service.py
backend/services/register_service.py --> backend/database/db.py
backend/services/attendance_service.py --> backend/database/db.py
backend/services/face_service.py --> face_engine/facenet/{detect,embedding}
backend/main.py --> backend/database/db.py
backend/main.py --> backend/api/routes.py
backend/main.py --> backend/services/faiss_search.py
backend/main.py --> face_engine/facenet/{detect,embedding}
```

## Dependency diagram (ASCII)

```text
frontend
  |
  | HTTP/WebSocket
  v
backend/api/routes.py
  |---> backend/services/register_service.py
  |       |---> backend/services/face_service.py
  |       |       |---> face_engine/facenet/detect.py
  |       |       `---> face_engine/facenet/embedding.py
  |       `---> backend/database/db.py
  |
  |---> backend/services/attendance_service.py
  |       `---> backend/database/db.py
  |
  |---> backend/services/faiss_search.py
  |       `---> [FAISS in-memory index]
  |
  `---> backend/database/db.py
  |
  `---> core/config.py
  |
  `---> backend/main.py (startup/orchestration)

backend/main.py
  |---> backend/database/db.py
  |---> backend/api/routes.py
  |---> backend/services/faiss_search.py
  `---> face_engine/facenet/{detect,embedding}
```

## Key coupling issues

### A. Route layer phụ thuộc nhiều vào DB

`backend/api/routes.py` import trực tiếp hơn 10 hàm từ `backend/database/db.py`.

- Ảnh hưởng: route không còn chỉ làm request/response, mà can thiệp nhiều vào dữ liệu.
- Gợi ý refactor: di chuyển tất cả thao tác DB vào service layer.

### B. FaceService làm quá nhiều việc

`backend/services/face_service.py` hiện xử lý:
- detect
- extract embedding
- liveness
- top-k
- recognize

- Ảnh hưởng: high coupling giữa business logic và AI model.
- Gợi ý: tách `Detector`, `Recognizer`, `Liveness`, `Search` vào module riêng.

### C. Dynamic import backend.main

`backend/api/routes.py` dùng dynamic import `from backend.main import faiss_index` và `init_faiss_index()`.

- Ảnh hưởng: làm code khó kiểm thử, tạo dependency loop tiềm ẩn.
- Gợi ý: quản lý FAISS index thông qua service hoặc object context, không import trực tiếp từ main.

### D. RegisterService phụ thuộc trực tiếp vào FaceService

Mặc dù đây là dependency hợp lý, nhưng hiện tại `FaceService` quá lớn nên `RegisterService` thừa nhận quá nhiều trách nhiệm.

### E. face_engine tĩnh liên kết với DeepFace

- `face_engine/facenet/*` ghép chặt với model DeepFace/Facenet512.
- Gợi ý: dùng abstraction interface để thay model dễ dàng.

## Critical dependency hotspots

- `backend/api/routes.py` (tập trung nhiều dependency)
- `backend/services/face_service.py` (AI + business logic mix)
- `backend/main.py` (startup + FAISS + warmup)
- `backend/database/db.py` (database single source)

## Suggested dependency improvements

### 1. Giảm coupling route → database

- Đổi route gọi service thay vì gọi `db.py` trực tiếp.
- Ví dụ: đưa `get_all_students`, `delete_student_and_embedding` vào `StudentService`.

### 2. Tách FaceService thành modules

- `DetectorService` hoặc `face_engine.detector.BaseDetector`
- `RecognizerService` hoặc `face_engine.recognizer.BaseRecognizer`
- `LivenessService`
- `SearchService` hoặc `FAISSEmbeddingIndex`

### 3. Tách FAISS khỏi main

- Tạo service `FaissService` quản lý index, build, add, search.
- Route/Service chỉ gọi FaissService.

### 4. Mở rộng `core/config.py`

- Thêm biến cấu hình `DETECTOR`, `RECOGNIZER`, `USE_FAISS`.

### 5. Giảm dependency circular

- Tránh import `backend.main` trong `routes.py`.
- Nếu cần shared object, dùng singleton service hoặc app.state.

## Practical refactor opportunities

| Problem | Existing dependency | Recommended fix |
|---|---|---|
| Route layer gọi DB trực tiếp | `backend/api/routes.py` → `backend/database/db.py` | Đổi sang `StudentService`, `EnrollmentService` |
| Single FaceService | `backend/services/register_service.py` → `backend/services/face_service.py` | Tách detector/recognizer/search/liveness |
| FAISS index được quản lý trong main | `backend/main.py` ↔ `backend/api/routes.py` | Đưa vào `backend/services/faiss_search.py` hoặc `FaissService` |
| DeepFace lock-in | `backend/services/face_service.py` → `face_engine/facenet` | Thêm `BaseDetector`/`BaseRecognizer` interfaces |

## Summary

Hệ thống hiện tại hoạt động, nhưng tồn tại rõ ràng những dependency khiến refactor khó:
- API layer quá phụ thuộc vào DB.
- AI logic chưa tách đủ.
- FAISS index được quản lý phân tán.
- DeepFace được dùng trực tiếp ở nhiều điểm.

Tài liệu `docs/dependency-analysis.md` này nên được dùng làm căn cứ đẩy nhanh phase 1-2 của roadmap: tách layer, giảm coupling và chuẩn hoá dependency.
