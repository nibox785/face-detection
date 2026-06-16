# User Requirements

## Stakeholders

- Quản trị viên / giáo viên
- Sinh viên
- Người phát triển dự án

## Mục tiêu người dùng

1. Giáo viên muốn điểm danh nhanh bằng khuôn mặt, giảm thao tác thủ công.
2. Quản trị viên muốn đăng ký sinh viên mới và quản lý dữ liệu dễ dàng.
3. Hệ thống phải báo cáo attendance chính xác và dễ tra cứu.
4. Dự án cần có benchmark để chứng minh hiệu năng.

## User stories

### Giáo viên

- Là một giáo viên, tôi muốn đăng nhập an toàn để quản lý điểm danh.
- Là một giáo viên, tôi muốn khởi tạo session điểm danh và xem trạng thái realtime.
- Là một giáo viên, tôi muốn xem danh sách sinh viên đã điểm danh hôm nay.

### Quản trị viên

- Là một quản trị viên, tôi muốn tạo và chỉnh sửa thông tin sinh viên.
- Là một quản trị viên, tôi muốn đăng ký khuôn mặt cho sinh viên bằng nhiều ảnh.
- Là một quản trị viên, tôi muốn kiểm tra trạng thái FAISS và embeddings.

### Sinh viên

- Là một sinh viên, tôi muốn được đăng ký khuôn mặt một cách đơn giản.
- Là một sinh viên, tôi muốn được điểm danh tự động khi hệ thống nhận diện chính xác.

## Functional requirements

- Hệ thống phải xác thực người dùng bằng JWT.
- Hệ thống phải cho phép đăng ký sinh viên và lưu embeddings.
- Hệ thống phải nhận diện khuôn mặt từ ảnh hoặc luồng realtime.
- Hệ thống phải lưu attendance theo ngày và không trùng lặp.

## Non-functional requirements

- Thời gian phản hồi `/recognize` < 1.5s cho pipeline hiện tại.
- Hệ thống phải có benchmark so sánh FPS/latency trước và sau refactor.
- Hệ thống phải dễ mở rộng để thay detector/recognizer.
- Việc thay đổi mô hình không được ảnh hưởng API frontend.

## Acceptance criteria

- API `POST /api/register` và `POST /api/recognize` hoạt động ổn định.
- Refactor phải giữ được chức năng hiện tại và có test xác nhận.
- Có ít nhất 1 benchmark baseline cho RetinaFace + FaceNet.
- Logging đủ để debug pipeline.
