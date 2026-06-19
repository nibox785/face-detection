# API Design

Contract API cho Face Attendance System. Runtime và module map: `backend.md`.

## Base URL

- HTTP API root: `/api`
- Health check: `GET /health` (ngoài prefix `/api`)
- Debug FAISS: `GET /debug/faiss-info` (ngoài prefix `/api`)
- WebSocket: `ws://<host>:<port>/api/ws/...` (cùng prefix `/api` với HTTP router)

## Authentication

- `POST /api/login`
  - Body JSON: `username`, `password`
  - Response: access token (JWT `HS256`, có `exp`, `jti`)
- `POST /api/logout`
  - Header: `Authorization: Bearer <token>`
  - Revoke token theo `jti` → bảng `revoked_tokens`
- `GET /api/auth/verify`
  - Header: `Authorization: Bearer <token>`
  - Kiểm tra token còn hiệu lực và chưa bị revoke

Các endpoint bảo mật (register, recognize, students, attendance, WebSocket) yêu cầu Bearer token hợp lệ.

## Student management

- `GET /api/students` — danh sách sinh viên
- `GET /api/students/{student_id}` — chi tiết sinh viên
- `PUT /api/students/{student_id}` — cập nhật **tên** (`name` bắt buộc, `multipart/form-data`)
- `DELETE /api/students/{student_id}` — xóa sinh viên và embeddings (cascade)

> `mssv` chỉ được gán khi đăng ký; chưa có API cập nhật `mssv` riêng.

## Attendance

- `GET /api/attendance` — lịch sử điểm danh
- `GET /api/attendance/export` — export Excel

## Registration endpoints

- `POST /api/register` — đăng ký một ảnh
- `POST /api/dataset/register` — đăng ký một ảnh + lưu `dataset/`
- `POST /api/dataset/register-multiple` — tối thiểu 10 ảnh, quality scoring (xem `backend.md`)
- `POST /api/face/check` — kiểm tra ảnh có khuôn mặt hợp lệ
- `POST /api/face/liveness-check` — kiểm tra liveness riêng

## Recognition

- `POST /api/recognize`
  - Body: `multipart/form-data`, field `file` (ảnh)
  - Response `data[]` mỗi face gồm: `student_id`, `name`, `score`, `bbox`, `top_candidates`, `liveness`, `decision`

### Decision thresholds (runtime)

Định nghĩa trong `backend/api/common.py`:

| `decision` | Điều kiện |
|------------|-----------|
| `AUTO_MARK` | score ≥ 0.66 |
| `MANUAL_REVIEW` | 0.48 ≤ score < 0.66 |
| `REJECT` | score < 0.48 |

Khi liveness `SUSPECT`, `AUTO_MARK` có thể yêu cầu score cao hơn ngưỡng mặc định.

## WebSocket realtime

Token truyền qua query: `?token=<jwt>`.

### `GET /api/ws/recognize`

Mode A — client gửi full frame và `track_hints[]` để server gắn `track_id`.

**Client → server**

- `{"type":"ping"}`
- `{"type":"frame","frame_id":"...","image":"data:image/jpeg;base64,...","track_hints":[...]}`

**Server → client**

- `{"type":"pong","ts": 171...}`
- `{"type":"recognize_result","frame_id":"...","results":[...]}`
- `{"type":"error","message":"...","frame_id":"..."}`

### `GET /api/ws/realtime/{session_id}`

Mode B — server-side tracking; trả `bbox` + `result` theo từng `track_id`.

**Client → server**

- `{"type":"ping"}`
- `{"type":"frame","frame_id":"...","image":"data:image/jpeg;base64,..."}`

**Server → client**

- `{"type":"pong","ts": 171...}`
- `{"type":"frame_result","session_id":"...","frame_id":"...","tracks":[{"track_id":"...","bbox":{...},"result":{...}}]}`
- `{"type":"error","session_id":"...","frame_id":"...","message":"..."}`

## Contract notes

- HTTP response mặc định JSON (`status`, `message`, `data` — xem schemas trong `backend/database/schemas.py`).
- Lỗi FastAPI: `{"detail": "..."}` kèm HTTP status.
- Upload ảnh: `Content-Type: multipart/form-data` (không set header thủ công khi dùng `FormData` ở browser).

## API stability during refactor

- Giữ nguyên endpoint và response shape hiện có.
- Refactor chỉ thay đổi nội bộ service/AI layer.
- Endpoint mới không được phá contract hiện có.

## Example payloads

### Login

```json
{ "username": "admin", "password": "admin123" }
```

### Recognize

Form-data:

- `file`: ảnh input

### Register

Form-data:

- `name`
- `mssv` (tùy chọn)
- `file`: ảnh

### Update student

Form-data:

- `name` (bắt buộc)

## Error handling

| Code | Ý nghĩa |
|------|---------|
| 400 | Bad request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not found |
| 413 | Payload too large |
| 500 | Server error |
