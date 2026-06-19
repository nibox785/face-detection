# Features

## Core features

- Đăng nhập quản trị viên bằng JWT.
- Đăng ký sinh viên và lưu trữ thông tin cơ bản (MSSV).
- Đăng ký khuôn mặt bằng ảnh đơn hoặc nhiều ảnh (burst capture + quality scoring).
- Nhận diện khuôn mặt và ghi attendance tự động (ảnh tĩnh + WebSocket realtime).
- Liveness check và decision logic (`AUTO_MARK`, `MANUAL_REVIEW`, `REJECT`).
- Search embedding với FAISS.
- Lưu attendance theo ngày và tránh ghi trùng.
- Export attendance Excel; import/export danh sách lớp từ frontend.
- REST API cho frontend React; CORS tương thích Vite.

## Current feature set

Contract đầy đủ: `08-api-design.md`. Tóm tắt:

- Auth: `POST /api/login`, `POST /api/logout`, `GET /api/auth/verify`
- Register: `POST /api/register`, `POST /api/dataset/register`, `POST /api/dataset/register-multiple`, `POST /api/face/check`, `POST /api/face/liveness-check`
- Recognize: `POST /api/recognize`, WebSocket `/api/ws/recognize`, `/api/ws/realtime/{session_id}`
- Students & attendance: CRUD sinh viên, `GET /api/attendance`, `GET /api/attendance/export`
- Debug: `GET /health`, `GET /debug/faiss-info`

## Refactor features (đang/plan)

- [x] Tách domain routers (`auth_routes`, `register_routes`, …) — Phase A
- [ ] `RecognitionPipeline` và tách `FaceService`
- [ ] Config `DETECTOR` / `RECOGNIZER` qua factory
- [ ] Base classes: `BaseDetector`, `BaseRecognizer`, `BaseSearchEngine`
- [ ] `FaissService` — bỏ FAISS global trong `main.py`
- [ ] Repository layer — route không gọi `db.py` trực tiếp

## Future feature candidates

- Thay RetinaFace bằng YOLOv11-face.
- Thay FaceNet512 bằng ArcFace.
- ByteTrack cho realtime (giảm embedding calls).
- Dashboard performance metrics trên UI.
- Pagination cho danh sách lớn.

## Feature priorities

1. Giữ chức năng hiện tại ổn định.
2. Tách module AI và business (Phase 1–2).
3. Đảm bảo API contract không đổi.
4. Benchmark và test coverage.
5. Đổi detector/recognizer mà không thay frontend.
