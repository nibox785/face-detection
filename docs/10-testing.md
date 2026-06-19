# Testing

Chiến lược test theo phase refactor: `07-implementation.md`.

## Goals

- Bảo đảm refactor không phá vỡ chức năng hiện tại.
- Tách biệt unit test và integration test.
- Có test cho AI pipeline, backend services, database, API.

## Test types

### Unit tests

- Detector / recognizer implementations (sau Phase 3–5).
- FAISS wrapper (`faiss_search.py`).
- `FaceService`, `RegisterService`, `AttendanceService`.
- DB helper functions (`backend/database/db.py`).

### Integration tests

- `POST /api/register`, `POST /api/dataset/register-multiple`
- `POST /api/recognize`
- `GET /api/students`, `PUT /api/students/{id}`, `DELETE /api/students/{id}`
- Auth: `/api/login`, `/api/logout`, `/api/auth/verify`
- WebSocket recognize/realtime (khi có harness)

### Regression tests

- `init_db()` migration flow.
- Embedding serialize/deserialize.
- Attendance duplicate check.
- FAISS index rebuild and search fallback.

## Existing test files

- `tests/test_api_core.py`
- `tests/test_detect_bbox.py`
- `tests/test_embedding_compat.py`
- `tests/test_face_engine.py`
- `tests/test_faiss.py`
- `tests/benchmark_faiss.py`

## Recommended coverage

- `backend/database/db.py`
- `backend/services/*.py`
- `backend/api/*_routes.py`, `common.py`
- `face_engine/facenet/*`
- `backend/main.py` startup flows

## Test framework

- Pytest; fixtures trong `tests/conftest.py`.
- SQLite test DB hoặc in-memory; `PYTEST_CURRENT_TEST` để skip warmup khi cần.

## How to run

```bash
pytest tests
```

## Tests theo phase refactor

| Phase | Thêm test |
|-------|-----------|
| 1 | `RecognitionPipeline` import/output; `FaceService` gọi pipeline |
| 2 | Factory switch `DETECTOR` / `RECOGNIZER` |
| 3 | `BaseDetector`, `RetinaFaceDetector` |
| 4 | `YoloFaceDetector` benchmark regression |
| 5 | `BaseRecognizer`, `FaceNetRecognizer`, `ArcFaceRecognizer` |
| 6 | Tracker + recognition integration |
| 7 | Benchmark report + API contract regression |

## Test naming conventions

- `test_<module>_<behavior>.py`
- Ví dụ: `test_face_service_recognize_faiss_fallback`

## Continuous validation

- `backend/main.py` startup + `GET /health`
- `tests/test_api_core.py` cover core API contract
- Tests nhanh và deterministic
