# Implementation Plan

## Refactor phases

### Phase 0: Freeze current state

- Ghi nhận kiến trúc hiện tại.
- Tạo tài liệu các phần overview, requirements, features, architecture.
- Chạy lại app và viết test cơ bản.
- Ghi benchmark baseline RetinaFace + FaceNet.

### Phase 1: Clean Architecture Refactor

- Tạo thư mục:
  - `face_engine/`
  - `detector/`
  - `recognizer/`
  - `search/`
  - `pipeline/`
- Di chuyển các hàm detect/embedding từ `face_engine/facenet/*`.
- Giữ service route hiện tại.
- Không đổi model hoặc API.

### Phase 2: Detector Abstraction

- Tạo `BaseDetector`.
- Tạo `RetinaFaceDetector` kế thừa.
- Thay import cũ bằng `detector = DetectorFactory.get_detector()`.
- Config `DETECTOR=retinaface`.

### Phase 3: YOLOv11-face

- Thêm `YoloFaceDetector`.
- Thử dùng ONNX/YOLO runtime.
- So sánh FPS/accuracy.
- Giữ API contract.

### Phase 4: Recognizer Abstraction

- Tạo `BaseRecognizer`.
- Thêm `FaceNetRecognizer` và `ArcFaceRecognizer`.
- Thay `get_embedding()` bằng `recognizer.embed(face_image)`.
- Khi dùng ArcFace, chuyển FAISS sang `IndexFlatIP`.

### Phase 5: ByteTrack Integration

- Thêm tracker module.
- Giảm embedding calls trong realtime stream.
- Flow:
  - Frame -> Detector -> Tracker -> Recognizer -> Search.

### Phase 6: Testing & Benchmark

- Unit tests cho:
  - Detector
  - Recognizer
  - FAISS index
  - Services
- Integration tests cho API route chính.
- Benchmark:
  - Latency recognize
  - FPS detect + recognition
  - Threshold accuracy

## Implementation details

### Module boundaries

- `face_engine/` chỉ chứa AI helper.
- `backend/services/` chứa business rules.
- `backend/api/` chỉ chứa routing.
- `backend/database/` chỉ chứa DB.

### Dependency inversion

- Services không import trực tiếp model cụ thể.
- Config `DETECTOR`, `RECOGNIZER` quyết định implementation.

### Configuration and environment

- `core/config.py` giữ tất cả biến môi trường.
- `DETECTOR=retinaface`.
- `RECOGNIZER=facenet`.
- `MODEL_WARMUP_ENABLED=1`.

### Database strategy

- Tiếp tục dùng SQLite.
- Embedding lưu định dạng binary có header.
- Migrate schema nhẹ khi cần.

### Deployment notes

- Giữ app chạy tốt với `uvicorn backend.main:app --reload`.
- CORS chỉ mở cho origin frontend.
- Thêm health check `/health`.

## Implementation checklist

- [ ] Di chuyển AI code vào `face_engine/`.
- [ ] Xây dựng `BaseDetector` và `BaseRecognizer`.
- [ ] Xây dựng `FAISSEmbeddingIndex` wrapper.
- [ ] Giữ các route hiện tại.
- [ ] Thêm tests cho từng module.
- [ ] Thêm benchmark và kết quả mẫu.
- [ ] Viết README ngắn gọn và roadmap refactor.
