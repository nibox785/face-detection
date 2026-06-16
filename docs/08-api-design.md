# API Design

## Base URL

- Backend API root: `/api`
- Health check: `/health`
- Debug FAISS info: `/debug/faiss-info`

## Authentication

- `POST /api/login`
  - request: `username`, `password`
  - response: access token
- `POST /api/logout`
  - invalidate token by `jti`
- `GET /api/auth/verify`
  - verify token validity

## Student management

- `GET /api/students`
  - trả về danh sách sinh viên.
- `GET /api/students/{student_id}`
  - trả về thông tin sinh viên.
- `PUT /api/students/{student_id}`
  - cập nhật `name` và/hoặc `mssv`.
- `DELETE /api/students/{student_id}`
  - xóa sinh viên và embeddings.

## Attendance

- `GET /api/attendance`
  - lấy lịch sử attendance.
- `GET /api/attendance/export`
  - export data (CSV/Excel) nếu có.

## Registration endpoints

- `POST /api/register`
  - upload ảnh đánh dấu một sinh viên.
- `POST /api/dataset/register`
  - upload ảnh cho dataset.
- `POST /api/dataset/register-multiple`
  - upload nhiều ảnh, có quality score.
- `POST /api/face/check`
  - kiểm tra ảnh có khuôn mặt hợp lệ.
- `POST /api/face/liveness-check`
  - kiểm tra liveness riêng.

## Recognition

- `POST /api/recognize`
  - nhận diện khuôn mặt từ ảnh.
  - response gồm `student_id`, `score`, `status`, `top_3_candidates`.

## WebSocket realtime (future)

- `GET /ws/realtime/{session_id}`
  - realtime frame stream recognition.
- `GET /ws/recognize?token=...`
  - realtime hỗ trợ `track_id` theo client.

## Contract notes

- Mọi endpoint đều trả về JSON.
- Error format:
  - `status_code`
  - `detail`
- Xác thực Bearer token cho endpoint bảo mật.
- `Content-Type: multipart/form-data` dùng với upload ảnh.

## API stability during refactor

- Giữ nguyên các endpoint hiện tại.
- Chỉ refactor nội bộ service/AI layer.
- Nếu cần thêm endpoint mới, không đổi contract hiện có.

## Example payloads

### Login

```json
{ "username": "admin", "password": "admin123" }
```

### Recognize

Form-data:
- `file`: ảnh input
```

### Register

Form-data:
- `name`
- `mssv`
- `file`: ảnh
```

## Response fields

- `success`: boolean
- `data`: payload
- `message`: text

## Error handling

- 400: bad request
- 401: unauthorized
- 403: forbidden
- 404: not found
- 413: payload too large
- 500: server error
