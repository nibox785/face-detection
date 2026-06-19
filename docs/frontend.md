# Frontend Documentation

Tài liệu frontend runtime. API contract: `08-api-design.md`.

## Tổng quan

Frontend dùng React + Vite, chia thành 3 tab chính sau khi đăng nhập:

- Đăng ký
- Điểm danh
- Danh sách

Mọi request backend đi qua `src/api/apiClient.js`.

## Cấu trúc chính

`frontend/src/`

- `main.jsx` — mount app và bọc `AuthProvider`.
- `App.jsx` — tab navigation, load students/attendance, logout.
- `context/AuthContext.jsx` — bootstrap token, verify token, logout on close.
- `api/apiClient.js` — `API_BASE`, token helper, `apiFetch`, auth helper.
- `components/features/`:
  - `LoginPanel.jsx`
  - `RegisterPanel.jsx`
  - `AttendancePanel.jsx`
  - `StudentsPanel.jsx`

## Auth flow

1. App khởi động, `AuthContext` đọc token từ `sessionStorage`.
2. Nếu có token, gọi `/api/auth/verify` để xác thực.
3. Nếu token sai/hết hạn, tự clear token và quay về login.
4. Đăng xuất: gọi `/api/logout`, clear token, `bestEffortLogoutOnClose` khi đóng tab.

Token là session-only (không dùng `localStorage` để auto-login sau khi đóng tab).

## RegisterPanel

Luồng burst capture:

- Mục tiêu thu 10 frame (`TARGET_FRAMES=10`).
- Preview check một số frame qua `/api/face/check`.
- Gửi tất cả frame qua `/api/dataset/register-multiple`.
- Hỗ trợ MSSV, reset state, đóng camera sau đăng ký thành công.

## AttendancePanel

- Overlay bbox smooth (tracking + prediction, 20–30 FPS draw loop).
- Recognize realtime qua WebSocket Mode B: FE gửi frame, backend detect + tracking, trả `track_id + bbox + result`.
- Telemetry: FPS, API calls/phút, latency gần nhất/trung bình.
- Decision stats: `AUTO_MARK`, `MANUAL_REVIEW`, `REJECT`.
- Top-3 candidates và score bar.
- Import danh sách lớp từ Excel, export kết quả điểm danh ra Excel.
- Export session: JSON (`session_metrics_*.json`), Excel telemetry.

## StudentsPanel

- Danh sách sinh viên + MSSV.
- Lịch sử điểm danh (20 bản ghi mới nhất trên UI).
- Sửa tên và xóa sinh viên.
- Refresh dữ liệu theo nhu cầu.

## State management

**Global** — `AuthContext`: access token, current user, authentication status.

**Local** — từng component: forms, modal, recognition results.

## Luồng giao tiếp

```
React Component → apiClient → FastAPI → JSON Response → UI Update
```

Realtime:

```
Camera → Frontend Capture → WebSocket → Backend Recognition → UI Update
```

## API client

Trong `apiClient.js`:

- `API_BASE = http://127.0.0.1:8000/api`
- `authHeaders()` tự động chèn Bearer token.
- `apiFetch()` xử lý 401 (clear token + reload).
- Không set `Content-Type` thủ công khi gửi `FormData`.
- WebSocket: `getWsOrigin()` → `ws://<host>:<port>/api`; endpoint đầy đủ `/api/ws/...` (xem `08-api-design.md`).

## Đồng bộ frontend–backend

- Payload update student phải khớp contract (`PUT /api/students/{student_id}`).
- Khi đổi contract API, cập nhật `apiClient` và panel liên quan cùng lúc.
