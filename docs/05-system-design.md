# System Design

## Architectural overview

Hệ thống chia thành 4 layer chính:

1. Frontend UI (React/Vite)
2. Backend API (FastAPI)
3. Service layer
4. AI/Engine layer + Database

### Logical components

- API Layer: `backend/api/routes.py`
- Service Layer:
  - `backend/services/face_service.py`
  - `backend/services/register_service.py`
  - `backend/services/attendance_service.py`
  - `backend/services/faiss_search.py`
- AI Engine Layer:
  - `face_engine/facenet/detect.py`
  - `face_engine/facenet/embedding.py`
- Database Layer: `backend/database/db.py`

## Current runtime flow

1. Client gửi request hoặc frame.
2. Route xác thực và gọi service.
3. FaceService detect face.
4. FaceService extract embedding.
5. Search FAISS hoặc loop cosine.
6. AttendanceService quyết định và ghi DB.
7. API trả kết quả.

## Target runtime flow

1. Client -> API -> RecognitionPipeline
2. Detector phát hiện bounding boxes.
3. Recognizer trích embedding.
4. Search Engine tìm top-k candidates.
5. Decision Engine xác định attendance.
6. Database lưu kết quả.

## Component responsibilities

### API Router

- Chỉ xử lý request/response.
- Xác thực JWT.
- Gọi service tương ứng.

### FaceService

- Tập trung vào detect/embedding/liveness.
- Không quản lý database.
- Không chứa logic API.

### RegisterService

- Quản lý đăng ký sinh viên.
- Lưu student metadata và embeddings.
- Cập nhật cache + FAISS.

### AttendanceService

- Kiểm tra attendance duplicate.
- Lưu log attendance.
- Trả về trạng thái attendance.

### FAISSEmbeddingIndex

- Xây dựng và truy vấn FAISS.
- Hỗ trợ incremental update.
- Báo cáo trạng thái index.

## Folder structure target

- `face_engine/`
  - `detector/`
  - `recognizer/`
- `pipeline/`
  - `recognition_pipeline.py`
- `backend/`
  - `api/`
  - `services/`
  - `database/`

## Refactor decomposition

### Phase 1

- Tách AI layer ra `face_engine/`.
- Giữ backend API hiện tại.
- Chỉ thay đổi đường dẫn import.

### Phase 2

- Thêm `BaseDetector`.
- Tạo `RetinaFaceDetector`.
- Load detector bằng config.

### Phase 3

- Thêm `YoloFaceDetector`.
- So sánh performance so với RetinaFace.

### Phase 4

- Thêm `BaseRecognizer`.
- Tạo `FaceNetRecognizer` và `ArcFaceRecognizer`.
- Nâng cấp FAISS nếu cần.

### Phase 5

- Thêm tracking (ByteTrack).
- Giảm embedding call trong stream.

## Cross-cutting concerns

- Logging: mỗi layer cần log rõ ràng.
- Config: cấu hình tập trung trong `core/config.py`.
- Health checks: `/health`, `/debug/faiss-info`.
- Testing: mỗi module có test đơn vị.
- Benchmark: tách benchmark và kết quả vào `benchmarks/`.
