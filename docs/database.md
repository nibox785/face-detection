# 🗄️ Database

## Các bảng

### students
- id
- name

### embeddings
- id
- student_id
- vector (BLOB)

### attendance
- id
- student_id
- timestamp

## Ghi chú
- embedding lưu dưới dạng BLOB
- sử dụng pickle để encode/decode