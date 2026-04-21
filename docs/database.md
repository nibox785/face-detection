# 🗄️ Database

## Tổng quan
Database sử dụng SQLite với file `attendance.db`.
Backend lưu:
- thông tin sinh viên
- embedding khuôn mặt
- lịch sử điểm danh

## File chính
- `backend/database/db.py` - logic kết nối, tạo bảng và thao tác dữ liệu.
- `backend/database/models.py` - phần init DB cũ/đơn giản hơn.
- `backend/database/schemas.py` - định nghĩa response model dùng cho API, không phải bảng SQL.

## Các bảng
### students
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `name` TEXT NOT NULL
- `mssv` TEXT UNIQUE
- `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP

### embeddings
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `student_id` INTEGER
- `embedding` BLOB
- `student_id` tham chiếu đến `students(id)` với `ON DELETE CASCADE`

### attendance
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `student_id` INTEGER
- `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP
- `student_id` tham chiếu đến `students(id)` với `ON DELETE CASCADE`

## Index
- `idx_student_id` trên bảng `embeddings(student_id)`
- `idx_attendance_student` trên bảng `attendance(student_id)`
- `idx_attendance_date` trên `attendance(DATE(timestamp))`

## Luồng dữ liệu chính
1. `init_db()` tạo các bảng và index.
2. `save_embedding(student_id, embedding)` lưu embedding dưới dạng BLOB nhị phân từ `numpy.float32`.
3. `get_all_embeddings()` tải tất cả embedding và giải mã theo format nhị phân mới; dữ liệu cũ bằng `pickle` vẫn đọc được.
4. `insert_attendance(student_id)` thêm bản ghi điểm danh mới.
5. `check_attendance_today(student_id)` kiểm tra nếu sinh viên đã được điểm danh hôm nay.
6. `get_all_students()` trả về danh sách sinh viên hiện có.
7. `get_student_by_id()`/`get_student_by_name()` tìm sinh viên theo ID hoặc tên.
8. `delete_student_and_embedding(student_id)` xóa bản ghi trong `students`, các bảng liên quan tự được dọn nhờ `ON DELETE CASCADE`.
9. `get_attendance_by_student(student_id)` trả về lịch sử điểm danh của một sinh viên.
10. `get_attendance_range(start_date, end_date)` trả về báo cáo điểm danh theo khoảng thời gian.

## Ghi chú kỹ thuật
- Embedding khuôn mặt được lưu trong cột `embedding` dưới dạng BLOB nhị phân.
- Dữ liệu embedding cũ từng lưu bằng `pickle` vẫn có thể đọc để tương thích ngược.
- Quan hệ giữa `students`, `embeddings`, `attendance` đảm bảo xóa dữ liệu liên quan khi xóa sinh viên, với điều kiện `PRAGMA foreign_keys = ON`.
- Dữ liệu attendance được truy vấn theo ngày bằng `DATE(timestamp)` để hỗ trợ báo cáo.

## Các API liên quan
- `/api/students` - lấy danh sách sinh viên
- `/api/students/{student_id}` - lấy chi tiết sinh viên
- `/api/students/{student_id}` (DELETE) - xóa sinh viên
- `/api/attendance` - lấy lịch sử điểm danh
- `/api/attendance/export` - xuất báo cáo CSV

