# Target Architecture

## Mục tiêu

Đề xuất này mô tả kiến trúc mục tiêu cho hệ thống điểm danh nhận diện khuôn mặt, hướng tới:
- tách rõ các trách nhiệm theo layer,
- giảm coupling giữa route, service, database và AI engine,
- sử dụng pattern singleton / shared service để quản lý tài nguyên dùng chung,
- mở rộng dễ dàng cho nhiều detector, recognizer, và pipeline mới.

## Vấn đề hiện tại

- Một số file hiện đảm nhiệm quá nhiều nhiệm vụ (`backend/api/routes.py`, `backend/services/face_service.py`, `backend/main.py`).
- Route layer gọi trực tiếp CRUD từ `backend/database/db.py`.
- FAISS index và AI models được khởi tạo lan truyền giữa `main`, `routes`, và service.
- `FaceService` hiện vừa xử lý detect, embedding, liveness, search, vừa phục vụ registration.
- DeepFace/Facenet lock-in chưa cho phép thay model hoặc triển khai backend extension dễ dàng.

## Nguyên tắc kiến trúc mục tiêu

1. **Thin route layer**
   - `backend/api/routes.py` chỉ định nghĩa endpoint và chuyển request tới service.
   - Không gọi trực tiếp DB hoặc quản lý index.

2. **Service layer rõ ràng**
   - Mỗi service chỉ chịu một nhóm trách nhiệm:
     - `StudentService`, `AttendanceService`, `RegisterService`, `FaissService`, `DetectorService`, `RecognizerService`, `LivenessService`.

3. **Shared singleton resources**
   - Dùng singleton cho tài nguyên nặng:
     - DB connection / session factory,
     - FAISS index,
     - detector/recognizer model instances,
     - cấu hình runtime.

4. **Dependency injection + app state**
   - Sử dụng FastAPI dependency hoặc `app.state` để chia sẻ service singleton.
   - Tránh import chu kỳ giữa `backend/main.py` và `backend/api/routes.py`.

5. **Abstraction layer cho AI engine**
   - Định nghĩa interface chung cho detector và recognizer:
     - `BaseDetector`, `BaseRecognizer`, `BaseLivenessDetector`.
   - Hiện tại vẫn dùng `RetinaFaceDetector`, `FaceNetRecognizer`, nhưng dễ đổi sang YOLO, ArcFace.

6. **Mở rộng theo phase roadmap**
   - architecture phải hỗ trợ:
     - thay detector không đổi API,
     - thêm recognizer mới,
     - tích hợp ByteTrack hoặc stream tracking,
     - benchmark và test các thành phần độc lập.

## Kiến trúc module đề xuất

### 1. Entry point: `backend/main.py`

Chỉ làm:
- tạo FastAPI app,
- load cấu hình,
- init DB,
- tạo singleton services,
- gắn router.

Không làm:
- xử lý business logic,
- truy vấn DB,
- truy vấn FAISS trực tiếp.

### 2. API layer: `backend/api/routes.py`

Chỉ thực hiện:
- nhận request,
- xác thực dữ liệu,
- gọi service phù hợp,
- trả về response.

Ví dụ:
- `POST /register` gọi `RegisterService.register_student(...)`
- `POST /attendance` gọi `AttendanceService.mark_attendance(...)`
- `GET /students` gọi `StudentService.list_students()`

### 3. Service layer

#### `backend/services/config_service.py`

- load and expose configuration.
- singleton runtime config.

#### `backend/services/db_service.py`

- quản lý SQLAlchemy / SQLite engine và session.
- cung cấp repository access.
- singleton.

#### `backend/services/face_services/detector_service.py`

- wrapper cho `BaseDetector`.
- load model một lần.
- cung cấp `detect_faces(image)`.

#### `backend/services/face_services/recognizer_service.py`

- wrapper cho `BaseRecognizer`.
- tạo embedding một lần.
- cung cấp `extract_embedding(image)`.

#### `backend/services/face_services/liveness_service.py`

- quản lý kiểm tra liveness.
- singleton model/threshold config.

#### `backend/services/faiss_service.py`

- quản lý index singleton,
- xử lý build, search, update,
- dùng `IndexFlatL2` hoặc cấu hình `IndexFlatIP`.

#### `backend/services/register_service.py`

- orchestration cho đăng ký học viên:
  - gọi `DetectorService`, `RecognizerService`, `DBService`.

#### `backend/services/attendance_service.py`

- orchestration cho điểm danh:
  - gọi `FaceService`/`SearchService`, `DBService`, `FaissService`.

#### `backend/services/student_service.py`

- xử lý CRUD students và embeddings.
- tách khỏi route.

### 4. Database layer: `backend/database`

- `db.py`: init schema, session provider, reusable CRUD helpers.
- `models.py`: ORM models.
- `schemas.py`: Pydantic request/response.
- `repositories/`: chọn nếu muốn tách repo pattern.

### 5. AI engine layer: `face_engine`

- `face_engine/detectors/base.py`
- `face_engine/detectors/retina.py`
- `face_engine/detectors/yolo.py`
- `face_engine/recognizers/base.py`
- `face_engine/recognizers/facenet.py`
- `face_engine/recognizers/arcface.py`
- `face_engine/liveness/base.py`
- `face_engine/liveness/face_liveness.py`

## Pattern singleton cụ thể

### FastAPI dependency singleton

Sử dụng `@lru_cache()` để tạo singleton dependency:

```python
from functools import lru_cache

from backend.services.config_service import ConfigService

@lru_cache()
def get_config_service() -> ConfigService:
    return ConfigService()
```

Route chỉ cần khai báo dependency:

```python
from fastapi import Depends

@app.post("/register")
def register(payload: RegisterPayload, config: ConfigService = Depends(get_config_service)):
    return RegisterService(config).register(payload)
```

### app.state shared object

Hoặc gán singleton service vào `app.state` trong `main.py`:

```python
app.state.faiss_service = FaissService(config)
```

Trong route/service, lấy bằng dependency function:

```python
def get_faiss_service(request: Request) -> FaissService:
    return request.app.state.faiss_service
```
```

## Đề xuất cấu trúc file mới

```
backend/
  main.py
  api/
    routes.py
  services/
    config_service.py
    db_service.py
    student_service.py
    attendance_service.py
    register_service.py
    faiss_service.py
    face_services/
      detector_service.py
      recognizer_service.py
      liveness_service.py
  database/
    db.py
    models.py
    schemas.py
    repositories.py
face_engine/
  detectors/
    base.py
    retina.py
    yolo.py
  recognizers/
    base.py
    facenet.py
    arcface.py
  liveness/
    base.py
    facenet_liveness.py
```

## Mở rộng hệ thống phù hợp singleton

1. **Đa detector / đa recognizer**
   - chỉ cần thêm class mới kế thừa interface.
   - registry hoặc config chọn implementation.

2. **Stream / realtime**
   - `FaissService` singleton giữ index và cache kết quả.
   - `DetectorService` singleton giữ model, giảm thời gian khởi tạo.

3. **Benchmark và test**
   - mỗi service có thể unit test độc lập.
   - singleton services dễ mock bằng dependency injection.

4. **Rõ trách nhiệm**
   - không file nào cả startup + business + data + AI.
   - chỉ `main.py` orchestration, `routes.py` forwarding, `services/` orchestration, `database/` persistence, `face_engine/` model.

## Lợi ích

- Giảm coupling và phụ thuộc vòng.
- Tăng khả năng mở rộng theo roadmap: YOLO, ArcFace, ByteTrack.
- Dễ bảo trì và dễ test.
- Singleton tài nguyên nặng giúp tiết kiệm bộ nhớ và thời gian khởi tạo.
- Thích hợp cho hệ thống thực tế, không chỉ portfolio proof-of-concept.

## Kết luận

`docs/target-architecture.md` nên là tài liệu chỉ dẫn cho phase 1-3 của roadmap:
- chuyển từ single-file responsibilities sang service singletons,
- chuẩn hóa dependency injection,
- tách AI pipeline thành module riêng,
- và làm cho backend dễ mở rộng cho nhiều detector/recognizer và realtime workflow.
