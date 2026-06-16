# Features

## Core features

- Đăng nhập quản trị viên bằng JWT.
- Đăng ký sinh viên và lưu trữ thông tin cơ bản.
- Đăng ký khuôn mặt bằng ảnh đơn hoặc nhiều ảnh.
- Nhận diện khuôn mặt và ghi attendance tự động.
- Search embedding với FAISS.
- Lưu attendance theo ngày và tránh ghi trùng.
- REST API cho frontend React.
- CORS cấu hình để tương thích với Vite.

## Current feature set

- `POST /api/register` để đăng ký khuôn mặt.
- `POST /api/recognize` để nhận diện và điểm danh.
- `GET /api/students` và `GET /api/attendance` để lấy dữ liệu.
- `DELETE /api/students/{id}` để xóa sinh viên.
- `GET /debug/faiss-info` để kiểm tra index FAISS.
- Websocket realtime flow cho điểm danh camera.

## Refactor features

- Tách pipeline AI thành modules có interface.
- Thêm `face_engine/` và `pipeline/` riêng.
- Hỗ trợ config `DETECTOR` và `RECOGNIZER`.
- Thêm base classes:
  - `BaseDetector`
  - `BaseRecognizer`
  - `BaseSearchEngine`
- Lưu chỉ mục FAISS theo định dạng dễ cập nhật.

## Future feature candidates

- Thay RetinaFace bằng YOLOv11-face.
- Thay FaceNet512 bằng ArcFace.
- Thêm tracking với ByteTrack cho realtime.
- Thêm export attendance CSV/Excel.
- Thêm quality scoring cho ảnh đăng ký.
- Thêm dashboard đơn giản cho performance metrics.

## Feature priorities

1. Giữ chức năng hiện tại ổn định.
2. Tách module AI và business.
3. Đảm bảo API contract không đổi.
4. Thêm benchmarks và test coverage.
5. Đổi detector/recognizer mà không thay frontend.
