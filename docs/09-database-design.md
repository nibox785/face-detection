# Database Design

## Overview

Hệ thống dùng SQLite với database file mặc định là `attendance.db`.

### Tables

#### `students`
- `id` INTEGER PRIMARY KEY
- `name` TEXT NOT NULL
- `mssv` TEXT UNIQUE
- `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP

#### `embeddings`
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `student_id` INTEGER REFERENCES `students(id)` ON DELETE CASCADE
- `embedding` BLOB

#### `attendance`
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `student_id` INTEGER REFERENCES `students(id)` ON DELETE CASCADE
- `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP

#### `revoked_tokens`
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
- Hỗ trợ fallback dữ liệu legacy pickle.

## Schema evolution

- `init_db()` thực hiện migration nhẹ nếu thiếu cột `mssv` hoặc `created_at`.
- Thiết kế để giữ backward compatibility với database cũ.

## Transaction patterns

- `save_embedding` insert từng embedding.
- `insert_attendance` chọn timestamp theo timezone UTC+7.
- `delete_student_and_embedding` xóa cascade.

## Usage by modules

- `backend/database/db.py` cung cấp toàn bộ CRUD.
- Services chỉ gọi hàm database, không trực tiếp connect SQLite.
- `backend/main.py` gọi `init_db()` khi startup.

## Future migration plan

### PostgreSQL

Khi cần production:
- Chuyển `sqlite3` sang `psycopg2` / `asyncpg`.
- Giữ schema tương tự.
- Chuyển `timestamp` sang `TIMESTAMP WITH TIME ZONE`.
- Thêm migration tool như Alembic.

## Data model summary

- Student 1:N Embedding
- Student 1:N Attendance

## Recovery / maintenance

- Cần bật `PRAGMA foreign_keys = ON`.
- Xóa student tự động xóa embedding + attendance.
- Nếu thay đổi format embedding, cập nhật `_serialize_embedding` và `_deserialize_embedding`.
