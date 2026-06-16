# Face Attendance System

## Overview

Face Attendance System là một dự án demo điểm danh bằng nhận diện khuôn mặt, xây dựng với:
- Backend: FastAPI
- Frontend: React + Vite
- AI: DeepFace / RetinaFace / FaceNet512
- Search: FAISS
- Database: SQLite

Hệ thống minh họa một pipeline nhận diện khuôn mặt đầy đủ, từ detect và embedding đến search, liveness check và attendance logging.

## What this repository shows

- Kiến trúc clean tách biệt API, business logic, AI engine và database.
- Khả năng thay đổi model mà không làm vỡ contract API.
- Sử dụng FAISS để tăng tốc tìm kiếm embedding.
- Data flow rõ ràng cho register, recognize và attendance.
- Benchmark và test coverage cơ bản.

## Current capabilities

- JWT auth cho admin.
- Register sinh viên và lưu khuôn mặt.
- Nhận diện mặt realtime / ảnh tĩnh.
- Liveness check và decision logic.
- Attendance logging theo ngày.
- Quản lý sinh viên, xem lịch sử attendance.
- WebSocket realtime support.

## Project structure

```text
face-detection/
|-- backend/
|   |-- main.py
|   |-- api/routes.py
|   |-- database/{db.py,models.py,schemas.py}
|   `-- services/{attendance_service.py,face_service.py,faiss_search.py,register_service.py}
|-- core/config.py
|-- face_engine/facenet/{detect.py,embedding.py}
|-- frontend/src/
|   |-- App.jsx
|   |-- api/apiClient.js
|   |-- context/AuthContext.jsx
|   `-- components/features/{LoginPanel.jsx,RegisterPanel.jsx,AttendancePanel.jsx,StudentsPanel.jsx}
|-- docs/
|   |-- architecture.md
|   |-- backend.md
|   |-- database.md
|   |-- frontend.md
|   |-- roadmap.md
|   |-- 01-project-overview.md
|   |-- 02-user-requirements.md
|   |-- 03-features.md
|   |-- 04-tech-solutions.md
|   |-- 05-system-design.md
|   |-- 06-ai-pipeline.md
|   |-- 07-implementation.md
|   |-- 08-api-design.md
|   |-- 09-database-design.md
|   |-- 10-testing.md
|   |-- 11-benchmark.md
|-- scripts/
|-- tests/
|-- requirements.txt
`-- requirements-dev.txt
```

## Quick start

### Backend

```powershell
cd d:\face-detection
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
python init_db.py
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd d:\face-detection\frontend
npm install
npm run dev
```

### Run tests

```powershell
cd d:\face-detection
& .\.venv\Scripts\Activate.ps1
pytest tests -q
```

## Important endpoints

### Authentication
- `POST /api/login`
- `POST /api/logout`
- `GET /api/auth/verify`

### Registration
- `POST /api/register`
- `POST /api/dataset/register`
- `POST /api/dataset/register-multiple`
- `POST /api/face/check`
- `POST /api/face/liveness-check`

### Recognition
- `POST /api/recognize`
- `GET /api/ws/realtime/{session_id}?token=...`

### Student & attendance
- `GET /api/students`
- `GET /api/students/{student_id}`
- `PUT /api/students/{student_id}`
- `DELETE /api/students/{student_id}`
- `GET /api/attendance`
- `GET /api/attendance/export`

## Configuration

Key settings in `core/config.py`:
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `SECRET_KEY`
- `ACCESS_TOKEN_EXPIRE_SECONDS`

Key runtime settings:
- `ALLOWED_ORIGINS`
- `MODEL_WARMUP_ENABLED`

## Benchmark

Scripts in `scripts/` support:
- latency benchmark (`benchmark_recognize_latency.py`)
- threshold evaluation (`benchmark_threshold.py`)
- session stability and liveness metrics

## Conclusion

Project này không chỉ là một hệ thống điểm danh bằng khuôn mặt; nó là một ví dụ về cách xây dựng một pipeline AI modular và dễ refactor.

- Nếu bạn muốn mở rộng: bắt đầu từ `docs/07-implementation.md` để thực hiện phase refactor.
- Nếu bạn muốn thay model: kiểm tra `docs/06-ai-pipeline.md` và `core/config.py`.
- Nếu bạn muốn đánh giá hiệu năng: xem `docs/11-benchmark.md` và `benchmarks/`.

Tóm lại: hệ thống đã hoạt động với FastAPI + React, có FAISS search và dữ liệu SQLite, và có tài liệu đầy đủ cho bước refactor tiếp theo.