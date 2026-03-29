# ⚙️ Backend

## Công nghệ
- FastAPI

## Chức năng
- Nhận request từ frontend
- Gọi FaceService để xử lý AI
- Trả kết quả nhận diện

## API chính
- POST /register: đăng ký sinh viên
- POST /recognize: nhận diện khuôn mặt
- GET /attendance: lấy danh sách điểm danh

## Cấu trúc
- main.py: entry point
- services/: xử lý logic
- database/: kết nối DB
- api/: định nghĩa route