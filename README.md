# 🎯 Face Attendance System

## 🚀 Tổng quan
Face Attendance System là hệ thống điểm danh sinh viên bằng nhận diện khuôn mặt.
Frontend React gửi ảnh lên backend FastAPI, backend xử lý face detection + face recognition bằng embedding FaceNet/DeepFace, so khớp bằng cosine similarity và lưu kết quả vào SQLite.

## 💡 Tính năng chính
- Đăng nhập admin
- Đăng ký sinh viên bằng ảnh hoặc camera
- Điểm danh tự động bằng webcam
- Nhận diện nhiều khuôn mặt trong ảnh
- Lưu lịch sử điểm danh
- Xem danh sách sinh viên
- Xuất báo cáo CSV
- Xóa sinh viên và dữ liệu điểm danh liên quan

## 🧠 Kiến trúc hệ thống
Frontend React (Vite)
→ Backend FastAPI
→ `backend/services/face_service.py`
→ `face_engine/facenet`
→ SQLite (`attendance.db`)

## 📁 Cấu trúc dự án
```
face-detection/
├── backend/
│   ├── main.py
│   ├── api/
│   │   └── routes.py
│   ├── database/
│   │   ├── db.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── services/
│   │   ├── face_service.py
│   │   ├── attendance_service.py
│   │   └── register_service.py
├── core/
│   └── config.py
├── dataset/
├── face_engine/
│   ├── facenet/
│   │   ├── detect.py
│   │   └── embedding.py
│   └── utils.py
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── styles.css
│       ├── api/
│       │   └── apiClient.js
│       ├── context/
│       │   └── AuthContext.jsx
│       └── components/
│           └── features/
│               ├── LoginPanel.jsx
│               ├── RegisterPanel.jsx
│               ├── AttendancePanel.jsx
│               └── StudentsPanel.jsx
├── docs/
│   ├── frontend.md
│   └── database.md
├── requirements.txt
├── README.md
└── init_db.py
```

## 🛠️ Công nghệ sử dụng
- Backend: Python, FastAPI, uvicorn
- AI: OpenCV, DeepFace, MTCNN, TensorFlow/Keras
- Frontend: React, Vite
- Database: SQLite
- Các thư viện hỗ trợ: python-multipart, pydantic

## Backend chi tiết
- `backend/main.py`: khởi tạo app FastAPI, CORS, cache embedding và lifecycle.
- `backend/api/routes.py`: định nghĩa endpoint REST API.
- `backend/services/face_service.py`: detect face, extract embedding, so sánh cosine similarity.
- `backend/services/register_service.py`: đăng ký sinh viên và lưu embedding.
- `backend/services/attendance_service.py`: lưu điểm danh và tránh trùng lặp ngày.
- `backend/database/db.py`: quản lý SQLite, tạo bảng, lưu/đọc embedding và truy vấn danh sách/attendance.
- `backend/database/models.py`: init DB đơn giản.
- `backend/database/schemas.py`: schema response API.
- `core/config.py`: cấu hình admin login và SECRET_KEY.

## Ghi chú kỹ thuật hiện tại
- Health check đã được sửa để không crash do import `datetime` sai.
- Nhận diện ưu tiên dùng FAISS index dùng chung thay vì build lại mỗi request.
- Khi đăng ký sinh viên, hệ thống ưu tiên kiểm tra theo MSSV để tránh gộp nhầm sinh viên trùng tên.
- Face detection đang lọc các bbox có confidence thấp để giảm ảnh nhiễu.
- Blacklist token đã chuyển sang lưu bền trong SQLite (`revoked_tokens`), không còn phụ thuộc bộ nhớ RAM.
- Cập nhật tên sinh viên đã đi qua database layer chung, không thao tác SQLite trực tiếp trong route.

## Thứ tự Sprint ưu tiên
- Sprint P0 (nghiêm trọng nhất): ổn định auth + nhất quán DB layer + an toàn xóa dữ liệu.
- Sprint P1: mở rộng test API và test tương thích dữ liệu để giảm regression.
- Sprint P2: tối ưu hiệu năng nhận diện (FAISS batch thật sự, warm-up model, benchmark threshold).

Chi tiết kế hoạch và điều kiện hoàn thành được mô tả trong docs/roadmap_v2.md.

Tiến độ hiện tại:
- Sprint P0: ✅ Hoàn thành.
- Sprint P1: 🔄 Đã mở rộng test API core (happy path + nhánh lỗi auth/validation), thêm coverage cho register-multiple/liveness-check và test tương thích embedding.
- Warning deprecation từ test client đã được giảm bằng cách dùng `httpx==0.26.0` cho môi trường test.
- Sprint P2: 🔄 Đã bắt đầu với tối ưu batch FAISS thật sự và warm-up model khi startup để giảm cold-start.

### Benchmark P2 (Latency + Threshold)
```powershell
cd d:face-detection
& .\.venv\Scripts\Activate.ps1

# 1) Benchmark độ trễ recognize: Loop vs FAISS single vs FAISS batch
python scripts/benchmark_recognize_latency.py --embeddings 1000 --queries 1000 --output benchmarks/p2_latency.json

# 2) Benchmark threshold trên dataset thực tế
python scripts/benchmark_threshold.py --dataset dataset --start 0.30 --end 0.90 --step 0.01 --output benchmarks/threshold_report.json
```

Kết quả benchmark sẽ nằm trong thư mục `benchmarks/` để dùng cho quyết định ngưỡng vận hành cuối cùng.

## Database
- File DB mặc định: `attendance.db`
- Bảng chính:
  - `students`: `id`, `name`, `mssv`, `created_at`
  - `embeddings`: `id`, `student_id`, `embedding`
  - `attendance`: `id`, `student_id`, `timestamp`

Embedding hiện được lưu dưới dạng `BLOB` nhị phân từ `numpy.float32` thay vì `pickle`.

Lưu ý: dữ liệu cũ lưu bằng `pickle` vẫn được đọc tương thích trong quá trình chuyển đổi.

Xóa sinh viên hiện dựa trên `ON DELETE CASCADE` sau khi bật `PRAGMA foreign_keys = ON`, nên chỉ cần xóa bản ghi trong `students` là hệ thống tự dọn các bảng liên quan.

## Frontend chi tiết
- `frontend/src/main.jsx`: render React app với `AuthProvider`.
- `frontend/src/App.jsx`: quản lý tab, điều hướng và tải dữ liệu.
- `frontend/src/context/AuthContext.jsx`: lưu token, trạng thái auth và logout.
- `frontend/src/api/apiClient.js`: gửi request API và thêm header token.
- `frontend/src/components/features/LoginPanel.jsx`: form đăng nhập admin.
- `frontend/src/components/features/RegisterPanel.jsx`: đăng ký sinh viên và chụp ảnh camera.
- `frontend/src/components/features/AttendancePanel.jsx`: điểm danh tự động, log và xuất CSV.
- `frontend/src/components/features/StudentsPanel.jsx`: xem danh sách, sửa tên, xóa sinh viên, xem lịch sử.

## Chạy dự án
### Backend
```powershell
cd d:face-detection
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
python init_db.py
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### Chạy test backend (Sprint P1)
```powershell
cd d:face-detection
& .\.venv\Scripts\Activate.ps1
pytest tests/test_api_core.py tests/test_embedding_compat.py tests/test_detect_bbox.py tests/test_faiss.py -q
```

### Frontend
```powershell
cd d:face-detection/frontend
npm install
npm run dev
```

## URLs
- Backend API: `http://127.0.0.1:8000`
- Frontend dev: `http://127.0.0.1:5173`

## Các endpoint chính
- `POST /api/login` — đăng nhập admin
- `POST /api/dataset/register` — đăng ký sinh viên và lưu ảnh dataset
- `POST /api/recognize` — điểm danh bằng ảnh
- `GET /api/students` — lấy danh sách sinh viên
- `PUT /api/students/{id}` — cập nhật tên sinh viên
- `DELETE /api/students/{id}` — xóa sinh viên
- `GET /api/attendance` — lấy lịch sử điểm danh
- `GET /api/attendance/export` — xuất báo cáo CSV

## Thiết lập admin
Mặc định admin login được cấu hình trong `core/config.py`:
- `ADMIN_USERNAME=admin`
- `ADMIN_PASSWORD=admin123`
- `SECRET_KEY=face-attendance-secret-key`

Có thể thay đổi bằng biến môi trường tương ứng.

## Lưu ý
- Hệ thống không training model, chỉ dùng model pretrained.
- `dataset/` lưu ảnh đăng ký sinh viên.
- `backend/database/db.py` là file xử lý SQLite chính.
- Frontend dùng `AuthContext` và `api/apiClient.js` để giữ auth token.

## Mở rộng
- Thêm trường `class` / `department` cho sinh viên
- Tăng cường xác thực bằng JWT thật sự
- Thêm quản lý lịch sử điểm danh chi tiết
- Bổ sung phân trang và tìm kiếm bảng danh sách
