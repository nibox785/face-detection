# Database Documentation

## 1) Tong quan

Database dung SQLite, file mac dinh: `attendance.db`.

Layer thao tac DB tap trung tai `backend/database/db.py`.

## 2) Schema hien tai

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

## 3) Index

- `idx_students_mssv_unique` tren `students(mssv)`
- `idx_student_id` tren `embeddings(student_id)`
- `idx_attendance_student` tren `attendance(student_id)`
- `idx_attendance_date` tren `attendance(DATE(timestamp))`
- `idx_revoked_tokens_exp` tren `revoked_tokens(exp_ts)`

## 4) Migration va backward compatibility

`init_db()` co migration nhe cho database cu:

- Them cot `mssv` va `created_at` neu chua ton tai.
- Tao index/constraint can thiet.
- Tao bang `revoked_tokens` cho logout ben vung.

Embedding duoc luu o format moi:

- `EMB1` + binary `float32` bytes.

Khi doc, he thong van fallback duoc du lieu cu luu bang pickle.

## 5) Cac ham DB duoc dung nhieu

- Student:
	- `create_student`, `get_all_students`, `get_student_by_id`, `get_student_by_name`, `get_student_by_mssv`
	- `update_student_name`, `update_student_mssv`, `delete_student_and_embedding`
- Embedding:
	- `save_embedding`, `get_all_embeddings`
- Attendance:
	- `insert_attendance`, `check_attendance_today`, `get_attendance_by_student`, `get_attendance_range`
- Token revoke:
	- `revoke_token`, `is_token_revoked`, `cleanup_revoked_tokens`

## 6) Timezone note

Attendance insert/check theo ngay dang su dung timezone UTC+7 (`VIETNAM_TZ`) trong `db.py`.

## 7) Luu y van hanh

- Luon bat `PRAGMA foreign_keys = ON` (da bat trong `get_connection()`).
- Xoa student chi can xoa bang `students`, du lieu lien quan duoc cascade.
- Neu doi format embedding, can cap nhat ca `_serialize_embedding` va `_deserialize_embedding`.

