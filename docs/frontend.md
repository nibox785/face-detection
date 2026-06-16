# Frontend Documentation

## 1) Tong quan

Frontend dung React + Vite, chia thanh 3 tab chinh sau khi dang nhap:

- Dang ky
- Diem danh
- Danh sach

Tat ca request backend di qua `src/api/apiClient.js`.

## 2) Cau truc chinh

`frontend/src/`

- `main.jsx`: mount app va boc `AuthProvider`.
- `App.jsx`: tab navigation, load students/attendance, logout.
- `context/AuthContext.jsx`: bootstrap token, verify token, logout on close.
- `api/apiClient.js`: API_BASE, token helper, `apiFetch`, auth helper.
- `components/features/`:
  - `LoginPanel.jsx`
  - `RegisterPanel.jsx`
  - `AttendancePanel.jsx`
  - `StudentsPanel.jsx`

## 3) Auth flow

1. App khoi dong, `AuthContext` doc token tu `sessionStorage`.
2. Neu co token, goi `/api/auth/verify` de xac thuc.
3. Neu token sai/het han, tu clear token va quay ve login.
4. Dang xuat:
   - goi `/api/logout`,
   - clear token,
   - co `bestEffortLogoutOnClose` khi dong tab.

Luu y: token dang la session-only (khong dung localStorage de auto-login lai sau khi dong tab).

## 4) RegisterPanel hien tai

`RegisterPanel.jsx` da doi sang luong burst capture:

- Muc tieu thu 10 frame (`TARGET_FRAMES=10`).
- Co preview check mot so frame bang `/api/face/check`.
- Gui tat ca frame qua `/api/dataset/register-multiple`.
- Ho tro MSSV, reset state, dong camera sau khi dang ky thanh cong.

## 5) AttendancePanel hien tai

`AttendancePanel.jsx` thuc hien:

- Overlay bbox smooth bang tracking + prediction ngan (20-30 FPS draw loop).
- Recognize realtime qua WebSocket (Mode B): FE gui frame, backend detect + tracking va tra `track_id + bbox + result`.
- Telemetry realtime: FPS, API calls/phut, latency gan nhat, latency trung binh.
- Decision stats: `AUTO_MARK`, `MANUAL_REVIEW`, `REJECT`.
- Hien top-3 candidates va score bar.
- Import danh sach lop tu Excel, export ket qua diem danh ra Excel.
- Export du lieu session:
  - JSON (`session_metrics_*.json`)
  - Excel telemetry.

## 6) StudentsPanel hien tai

- Hien danh sach sinh vien + MSSV.
- Hien lich su diem danh (20 ban ghi moi nhat tren UI).
- Ho tro sua ten va xoa sinh vien.
- Co refresh du lieu theo nhu cau.

## 7) State Management

## Global State

AuthContext

Stores:

- Access token
- Current user
- Authentication status

---

## Local State

Components manage:

- Forms
- Modal state
- Recognition results

## 8) API Communication

React Component
↓
apiClient
↓
FastAPI Endpoint
↓
JSON Response
↓
UI Update

## 9) Realtime Flow

Camera
↓
Frontend Capture
↓
WebSocket
↓
Backend Recognition
↓
Recognition Result
↓
UI Update

## 10) API client

Trong `apiClient.js`:

- `API_BASE = http://127.0.0.1:8000/api`
- `authHeaders()` tu dong chen Bearer token.
- `apiFetch()` tu dong xu ly 401 (clear token + reload).
- Khong set `Content-Type` thu cong khi gui `FormData`.
- WebSocket URL duoc build tu server origin (khong bao gom `/api`) vi WS endpoint nam o root: `/ws/...`.

## 11) Luu y dong bo frontend-backend

- Payload update student can duoc giu dong bo voi contract backend (`PUT /students/{student_id}`).
- Neu thay doi contract API, can cap nhat `apiClient` va panel lien quan cung luc.
