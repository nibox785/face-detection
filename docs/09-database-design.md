# Database Design

## Overview

Hệ thống dùng SQLite với database file mặc định là `attendance.db`.

Layer thao tác DB tập trung tại `backend/database/db.py`. Services chỉ gọi hàm database, không trực tiếp kết nối SQLite. `backend/main.py` gọi `init_db()` khi startup.

## Tables

### `students`

- `id` INTEGER PRIMARY KEY
- `name` TEXT NOT NULL
- `mssv` TEXT UNIQUE
- `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP

### `embeddings`

- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `student_id` INTEGER REFERENCES `students(id)` ON DELETE CASCADE
- `embedding` BLOB

### `attendance`

- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `student_id` INTEGER REFERENCES `students(id)` ON DELETE CASCADE
- `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP

### `revoked_tokens`

- `jti` TEXT PRIMARY KEY
- `exp_ts` INTEGER NOT NULL
- `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP

## Indexes

- `idx_students_mssv_unique` trên `students(mssv)`
- `idx_student_id` trên `embeddings(student_id)`
- `idx_attendance_student` trên `attendance(student_id)`
- `idx_attendance_date` trên `attendance(DATE(timestamp))`
- `idx_revoked_tokens_exp` trên `revoked_tokens(exp_ts)`

## Embedding storage

- Embedding lưu dưới dạng binary: `EMB1` header + float32 bytes.
- Hỗ trợ fallback dữ liệu legacy pickle khi đọc.

## Schema evolution

`init_db()` thực hiện migration nhẹ cho database cũ:

- Thêm cột `mssv` và `created_at` nếu chưa tồn tại.
- Tạo index/constraint cần thiết.
- Tạo bảng `revoked_tokens` cho logout bền vững.
- Thiết kế giữ backward compatibility với database cũ.

## Entity relationship

```
Student
│
├── Embedding
│
└── Attendance
```

- Student 1:N Embedding
- Student 1:N Attendance

## Data ownership

**Students** — thông tin sinh viên và metadata đăng ký.

**Embeddings** — face embeddings và dữ liệu mapping FAISS.

**Attendance** — lịch sử điểm danh và timestamp.

## Database API

Các hàm trong `backend/database/db.py` được dùng nhiều nhất:

**Student**

- `create_student`, `get_all_students`, `get_student_by_id`, `get_student_by_name`, `get_student_by_mssv`
- `update_student_name`, `update_student_mssv`, `delete_student_and_embedding`

**Embedding**

- `save_embedding`, `get_all_embeddings`

**Attendance**

- `insert_attendance`, `check_attendance_today`, `get_attendance_by_student`, `get_attendance_range`

**Token revoke**

- `revoke_token`, `is_token_revoked`, `cleanup_revoked_tokens`

## Transaction patterns

- `save_embedding` insert từng embedding.
- `insert_attendance` chọn timestamp theo timezone UTC+7 (`VIETNAM_TZ` trong `db.py`).
- `delete_student_and_embedding` xóa cascade.

## Timezone

Attendance insert/check theo ngày sử dụng timezone UTC+7 (`VIETNAM_TZ`) trong `db.py`.

## Future migration plan

### PostgreSQL

Khi cần production:

- Chuyển `sqlite3` sang `psycopg2` / `asyncpg`.
- Giữ schema tương tự.
- Chuyển `timestamp` sang `TIMESTAMP WITH TIME ZONE`.
- Thêm migration tool như Alembic.

Lý do: concurrency tốt hơn, indexing tốt hơn, phù hợp triển khai production.

## Recovery / maintenance

- Luôn bật `PRAGMA foreign_keys = ON` (đã bật trong `get_connection()`).
- Xóa student chỉ cần xóa bảng `students`; dữ liệu liên quan được cascade.
- Nếu thay đổi format embedding, cập nhật `_serialize_embedding` và `_deserialize_embedding`.
