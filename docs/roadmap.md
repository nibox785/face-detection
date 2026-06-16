# Roadmap

## Mục tiêu

Kết luận roadmap refactor cho hệ thống điểm danh bằng nhận diện khuôn mặt.

## Tóm tắt hiện trạng

- Backend: Python + FastAPI
- Frontend: React + Vite
- AI: DeepFace / RetinaFace / FaceNet512
- Search: FAISS
- DB: SQLite

Hiện tại:
Image → Detect (RetinaFace) → Embedding (FaceNet512) → FAISS → Decision → SQLite

## Các vấn đề chính

- FaceService làm quá nhiều nhiệm vụ.
- Business layer phụ thuộc trực tiếp vào DeepFace.
- AI pipeline rải rác trong route và service.
- DeepFace xử lý cả detect, embedding, liveness.

## Kiến trúc mục tiêu

React → FastAPI → Recognition Pipeline → Attendance Service → SQLite

Recognition Pipeline:
Frame → Detector → Recognizer → Search → Decision → Attendance

## Các phase chính

1. **Phase 0 – Freeze current state**
   - Hiểu hệ thống và tạo docs chi tiết.

2. **Phase 1 – Clean Architecture Refactor**
   - Tách AI layer khỏi business.
   - Giữ nguyên model.
   - Tạo các module rõ ràng.

3. **Phase 2 – Detector Abstraction**
   - Thêm `BaseDetector`.
   - Implement `RetinaFaceDetector` và `YoloFaceDetector`.

4. **Phase 3 – YOLOv11-face Migration**
   - Đổi detector sang YOLO.
   - Giữ API không đổi.

5. **Phase 4 – ArcFace Migration**
   - Thêm `BaseRecognizer`.
   - Implement `FaceNetRecognizer` và `ArcFaceRecognizer`.
   - FAISS chuyển từ `IndexFlatL2` sang `IndexFlatIP` khi cần.

6. **Phase 5 – ByteTrack Integration**
   - Tăng FPS realtime.
   - Giảm embedding calls trong stream.

7. **Phase 6 – Testing & Benchmark**
   - Unit, integration và API tests.
   - Benchmark FPS, latency, accuracy.

## Tài liệu chi tiết

- `docs/01-project-overview.md`
- `docs/02-user-requirements.md`
- `docs/03-features.md`
- `docs/04-tech-solutions.md`
- `docs/05-system-design.md`
- `docs/06-ai-pipeline.md`
- `docs/07-implementation.md`
- `docs/08-api-design.md`
- `docs/09-database-design.md`
- `docs/10-testing.md`
- `docs/11-benchmark.md`

## Mục tiêu cuối cùng

YOLOv11-face → ByteTrack → ArcFace → FAISS → FastAPI → React

Đủ để thể hiện:
- Computer Vision
- Face Recognition
- Backend API
- Vector Search
- System Design
- Performance Optimization

Không over-engineering, phù hợp portfolio cá nhân.
