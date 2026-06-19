# Implementation Plan

Kế hoạch refactor từng bước. Kiến trúc mục tiêu: `05-system-design.md`. Dependency hiện tại: `dependency-analysis.md`.

## Nguyên tắc thực hiện

Refactor incremental, không phá chức năng production. **Mỗi phase phải:**

- Build successfully
- Run successfully
- Be testable
- Be rollbackable

## Ánh xạ phase

| Phase | Tên | Trạng thái | Tương đương (legacy A→I) |
|-------|-----|------------|--------------------------|
| 0 | Freeze current state | Đang/largely done | — |
| A | Route separation | **Xong** | A |
| 1 | Recognition pipeline + clean architecture | Chưa | B |
| 2 | Configuration refactor | Chưa | E |
| 3 | Detector abstraction | Chưa | C |
| 4 | YOLOv11-face | Chưa | F |
| 5 | Recognizer + ArcFace | Chưa | D, G |
| 6 | ByteTrack | Chưa | H |
| 7 | Testing & benchmark | Một phần | I |

---

## Phase 0: Freeze current state

- Ghi nhận kiến trúc hiện tại.
- Tạo tài liệu overview, requirements, features, system design.
- Chạy lại app và viết test cơ bản.
- Ghi benchmark baseline RetinaFace + FaceNet.

---

## Phase A: Route separation ✅

**Trạng thái: hoàn thành**

Tách `routes.py` monolith thành:

- `auth_routes.py`
- `register_routes.py`
- `recognize_routes.py`
- `attendance_routes.py`
- `websocket_routes.py`
- `common.py`
- `routes.py` (aggregator)

**Deliverable:** API layer nhỏ hơn, dễ bảo trì.

**Còn lại:** route vẫn gọi `db.py` trực tiếp; FAISS import từ `main` — xử lý ở Phase 1–2.

---

## Phase 1: Recognition pipeline + clean architecture

**Deliverable:** Single recognition entry point.

Tạo cấu trúc:

```
face_engine/
  detector/
  recognizer/
  search/
  liveness/
  pipeline/
    recognition_pipeline.py
```

- Di chuyển logic detect/embedding từ `face_engine/facenet/*` vào abstraction.
- Tạo `RecognitionPipeline`: Detection → Embedding → Liveness → Search → Decision.
- Giữ service/route hiện tại; không đổi model hoặc API contract.
- Bắt đầu tách `FaceService` — services gọi pipeline thay vì model trực tiếp.

---

## Phase 2: Configuration refactor

**Deliverable:** Không còn model-specific logic trong services.

Tập trung runtime tại `core/config.py`:

- `DETECTOR=retinaface`
- `RECOGNIZER=facenet`
- `ENABLE_LIVENESS=true`
- `ENABLE_TRACKING=true`
- `MODEL_WARMUP_ENABLED=1`

Factory/registry chọn implementation theo config.

---

## Phase 3: Detector abstraction

**Deliverable:** Có thể thay detector.

- Tạo `BaseDetector`.
- Implement `RetinaFaceDetector`.
- Thay import cũ: `detector = DetectorFactory.get_detector()`.
- Config `DETECTOR=retinaface`.

---

## Phase 4: YOLOv11-face integration

**Deliverable:** Detector benchmark.

- Thêm `YoloFaceDetector` (ONNX/YOLO runtime).
- Switch `DETECTOR=yolo`.
- So sánh FPS/accuracy với RetinaFace.
- Giữ API contract.

---

## Phase 5: Recognizer + ArcFace

**Deliverable:** Recognition benchmark.

- Tạo `BaseRecognizer`.
- Implement `FaceNetRecognizer`, `ArcFaceRecognizer`.
- Thay `get_embedding()` → `recognizer.embed(face_image)`.
- Switch `RECOGNIZER=arcface` khi sẵn sàng.
- FAISS: `IndexFlatL2` → `IndexFlatIP` nếu embedding đã normalize.

---

## Phase 6: ByteTrack integration

**Deliverable:** Realtime optimization.

- Thay OpenCV tracker → ByteTrack.
- Giảm embedding calls trong realtime stream.
- Flow: Frame → Detector → Tracker → Recognizer → Search.

---

## Phase 7: Testing & benchmark

**Deliverable:** Portfolio-ready benchmark report.

Tài liệu: `10-testing.md`, `11-benchmark.md` (đã có).

**Unit tests:** Detector, Recognizer, FAISS index, Services.

**Integration tests:** `POST /register`, `POST /recognize`, auth flow, students CRUD.

**Benchmark metrics:** FPS, latency, accuracy, recognition time, FAISS query time.

---

## Implementation details

### Module boundaries

- `face_engine/` — AI primitives và pipeline.
- `backend/services/` — business rules.
- `backend/api/` — routing only (mục tiêu).
- `backend/database/` — persistence.

### Dependency inversion

- Services không import model cụ thể.
- `DETECTOR`, `RECOGNIZER` quyết định implementation.

### Database strategy

- Tiếp tục SQLite — chi tiết `09-database-design.md`.
- Embedding binary có header `EMB1`; migrate schema nhẹ khi cần.

### Deployment notes

- `uvicorn backend.main:app --reload`
- CORS chỉ mở origin frontend (`ALLOWED_ORIGINS`).
- Health: `GET /health`, `GET /debug/faiss-info`
- WebSocket: cần `uvicorn[standard]`

---

## Implementation checklist

- [x] Phase A: Tách domain routers (`*_routes.py`, `common.py`).
- [ ] Tạo `RecognitionPipeline` và tách logic khỏi `FaceService`.
- [ ] Di chuyển AI code vào `face_engine/` với abstraction.
- [ ] Xây dựng `BaseDetector` và `BaseRecognizer`.
- [ ] Tập trung config `DETECTOR` / `RECOGNIZER` trong `core/config.py`.
- [ ] Tách FAISS khỏi `main` → `FaissService` hoặc `app.state`.
- [ ] Loại bỏ gọi `db.py` trực tiếp từ `*_routes.py`.
- [ ] `FAISSEmbeddingIndex` wrapper ổn định (đã có — hoàn thiện API service).
- [ ] Giữ API contract — xem `08-api-design.md`.
- [ ] Tests từng module — xem `10-testing.md`.
- [ ] Benchmark và báo cáo — xem `11-benchmark.md`.
- [x] README và roadmap docs.
