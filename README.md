# Face Attendance System

He thong diem danh khuon mat (FastAPI + React) voi nhan dien FaceNet512/DeepFace, liveness gate, FAISS search va SQLite.

## Tong quan
- Frontend React (Vite) gui frame camera len backend.
- Backend detect khuon mat (RetinaFace), trich xuat embedding (Facenet512), kiem tra liveness, nhan dien bang cosine similarity + FAISS.
- Ket qua diem danh va du lieu sinh vien duoc luu vao SQLite `attendance.db`.

## Tinh nang hien tai
- Dang nhap/kiem tra phien dang nhap admin bang JWT.
- Dang ky sinh vien theo 1 anh hoac nhieu anh (10 frame) va luu dataset.
- Kiem tra nhanh khuon mat truoc dang ky (`/face/check`).
- Liveness check rieng (`/face/liveness-check`).
- Diem danh realtime (`/recognize`) voi top-3 ung vien va decision (`AUTO_MARK`, `MANUAL_REVIEW`, `REJECT`).
- Diem danh realtime qua WebSocket theo `track_id` (FE giu bbox local): `GET /api/ws/realtime/{session_id}?token=...`.
- Quan ly sinh vien: xem danh sach, lay chi tiet, doi ten, xoa.
- Xem lich su diem danh, loc theo student/date, export CSV.
- Token revoke duoc luu ben vung trong bang `revoked_tokens`.

## Cong nghe
- Backend: Python, FastAPI, Uvicorn
- AI/CV: OpenCV, DeepFace (RetinaFace + Facenet512)
- Search: FAISS
- Frontend: React 18, Vite
- Database: SQLite

## Cau truc thu muc chinh
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
|   `-- roadmap_v2.md
|-- scripts/
|-- tests/
|-- requirements.txt
`-- requirements-dev.txt
```

## Chay du an

### 1) Backend
```powershell
cd d:\face-detection
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
python init_db.py
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Luu y: WebSocket can `uvicorn[standard]` (da duoc khai bao trong `requirements.txt`). Neu ban da cai tu truoc, hay chay lai `pip install -r requirements.txt` de cap nhat.

### GPU (tuy chon)

- Tren Windows, TensorFlow pip thuong **khong nhan CUDA GPU** (nhin thay `[]`).
- Neu muon backend dung GPU (NVIDIA RTX), hay chay backend trong **WSL2** theo huong dan: `docs/gpu_wsl2.md`.

### 2) Frontend
```powershell
cd d:\face-detection\frontend
npm install
npm run dev
```

### 3) Test backend core
```powershell
cd d:\face-detection
& .\.venv\Scripts\Activate.ps1
pytest tests/test_api_core.py tests/test_embedding_compat.py tests/test_detect_bbox.py tests/test_faiss.py -q
```

## URL mac dinh
- Backend API: http://127.0.0.1:8000
- Frontend dev: http://127.0.0.1:5173

## API endpoint hien tai

### Auth
- POST `/api/login`
- POST `/api/logout`
- GET `/api/auth/verify`

### Register va face utilities
- POST `/api/register`
- POST `/api/dataset/register`
- POST `/api/dataset/register-multiple`
- POST `/api/face/check`
- POST `/api/face/liveness-check`

### Recognize
- POST `/api/recognize`
- WebSocket: `GET /api/ws/realtime/{session_id}?token=...` (track_id mode)

### Student va attendance management
- GET `/api/students`
- GET `/api/students/{student_id}`
- PUT `/api/students/{student_id}`
- DELETE `/api/students/{student_id}`
- GET `/api/attendance`
- GET `/api/attendance/export`

## Cau hinh quan trong
Trong `core/config.py`:
- `ADMIN_USERNAME` (mac dinh: `admin`)
- `ADMIN_PASSWORD` (mac dinh: `admin123`)
- `SECRET_KEY` (mac dinh: `face-attendance-secret-key`)
- `ACCESS_TOKEN_EXPIRE_SECONDS` (mac dinh: `3600`)

Trong `backend/main.py`:
- `ALLOWED_ORIGINS` (mac dinh: `http://127.0.0.1:5173,http://localhost:5173`)
- `MODEL_WARMUP_ENABLED` (`1`/`0`, mac dinh: `1`)

## Benchmark P2
```powershell
cd d:\face-detection
& .\.venv\Scripts\Activate.ps1

# latency: loop vs FAISS single vs FAISS batch
python scripts/benchmark_recognize_latency.py --embeddings 1000 --queries 1000 --output benchmarks/p2_latency.json

# threshold sweep
python scripts/benchmark_threshold.py --dataset dataset --start 0.30 --end 0.90 --step 0.01 --output benchmarks/threshold_report.json
```

## Tai lieu tham chieu
- `docs/architecture.md`: kien truc tong the
- `docs/backend.md`: backend layer + endpoint + luong nghiep vu
- `docs/frontend.md`: luong UI va API client
- `docs/database.md`: schema SQLite + migration notes
- `docs/roadmap_v2.md`: roadmap chi tiet (nguon chinh)
- `docs/roadmap.md`: ban tom tat dong bo theo roadmap v2
