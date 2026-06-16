# Testing

## Goals

- Bảo đảm refactor không phá vỡ chức năng hiện tại.
- Tách biệt unit test và integration test.
- Có test cho AI pipeline, backend services, database, API.

## Test types

### Unit tests

- Detector implementations.
- Recognizer implementations.
- FAISS wrapper.
- FaceService logic.
- RegisterService logic.
- AttendanceService logic.
- DB helper functions.

### Integration tests

- `POST /api/register`
- `POST /api/recognize`
- `GET /api/students`
- `PUT /api/students/{id}`
- `DELETE /api/students/{id}`
- Auth flow `/api/login`, `/api/logout`, `/api/auth/verify`

### Regression tests

- `init_db()` migration flow.
- Embedding serialize/deserialze.
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
- `backend/api/routes.py`
- `face_engine/facenet/*`
- `backend/main.py` startup flows

## Test framework

- Pytest.
- Fixtures trong `tests/conftest.py`.

## Test environment

- Sử dụng SQLite test database hoặc in-memory DB.
- Bật `PYTEST_CURRENT_TEST` để skip warmup nếu cần.

## How to run

```bash
pytest tests
```

## Add tests for refactor

### After Phase 1

- Test AI helper module import và function output.
- Test `FaceService.detect()`/`extract_embedding()`.

### After Phase 2

- Test `BaseDetector` và `RetinaFaceDetector`.
- Test detector factory config switch.

### After Phase 4

- Test `BaseRecognizer` và `FaceNetRecognizer`.
- Test `ArcFaceRecognizer` if implemented.

### After Phase 5

- Test tracker + recognition integration.

## Test naming conventions

- `test_<module>_<behavior>.py`
- Use descriptive names, e.g. `test_face_service_recognize_faiss_fallback`

## Continuous validation

- `backend/main.py` app startup should pass health check.
- `tests/test_api_core.py` should cover core API contract.
- Keep tests fast and deterministic.
