# 🚀 Roadmap V2 - Face Attendance System

## Mục tiêu tổng quan
- Chuyển từ bản prototype (mock AI) sang hệ thống nhận diện thật với FaceNet + MTCNN.
- Ổn định backend, chuẩn hóa frontend và hoàn thiện demo đồ án.

## Phase 0 - Đánh giá hiện trạng (1-2 ngày)
### Mục tiêu
- Chốt những phần đã xong và phần còn thiếu.

### Việc cần làm
- Rà soát toàn bộ API đang dùng ở frontend/backend.
- Xác nhận schema database cuối cùng (`students`, `embeddings`, `attendance`).
- Ghi rõ phần nào đang là mock AI để tránh nhầm với production.

### Deliverables
- Tài liệu trạng thái hệ thống hiện hành.
- Danh sách issue ưu tiên theo mức độ ảnh hưởng.

---

## Phase 1 - AI Core thật (FaceNet + MTCNN) (3-5 ngày)
### Mục tiêu
- Thay hoàn toàn mock detect/embedding bằng model thật.

### Việc cần làm
- Tích hợp MTCNN cho detect khuôn mặt.
- Tích hợp FaceNet để trích xuất embedding 512-d.
- Chuẩn hóa tiền xử lý ảnh (crop, resize, normalize).
- Thiết lập ngưỡng similarity ban đầu (threshold tuning).

### Deliverables
- `detect.py` chạy model MTCNN thật.
- `embedding.py` chạy FaceNet thật.
- Script benchmark ngưỡng nhận diện.

### KPI
- Nhận diện đúng trong điều kiện ánh sáng bình thường >= 90% trên tập test nội bộ.

---

## Phase 2 - Backend ổn định và an toàn (2-4 ngày)
### Mục tiêu
- Hoàn thiện API và chuẩn lỗi phản hồi.

### Việc cần làm
- Chuẩn hóa endpoint register/recognize/attendance.
- Bổ sung validate ảnh (định dạng, dung lượng, ảnh lỗi).
- Tối ưu cache embeddings và cơ chế reload cache.
- Hoàn thiện auth admin cho toàn bộ endpoint quản trị.
- Viết test API mức cơ bản (happy path + bad input).

### Deliverables
- Bộ API ổn định dùng cho frontend.
- Test backend cơ bản chạy pass.

---

## Phase 3 - Frontend quản trị hoàn chỉnh (2-4 ngày)
### Mục tiêu
- Trải nghiệm admin đầy đủ cho vận hành lớp.

### Việc cần làm
- Hoàn thiện login/logout và xử lý token hết hạn.
- Đăng ký sinh viên bằng camera nhiều frame.
- Điểm danh realtime với bounding box + tên.
- Quản lý sinh viên: xem, sửa, xóa.
- Lịch sử điểm danh: lọc theo ngày/MSSV/sinh viên.
- Xuất CSV báo cáo.

### Deliverables
- UI hoàn chỉnh cho demo end-to-end.
- Không còn lỗi flow chính khi thao tác liên tục.

---

## Phase 4 - Chất lượng nhận diện và dữ liệu (2-3 ngày)
### Mục tiêu
- Tăng độ ổn định khi chạy thực tế.

### Việc cần làm
- Bổ sung quality check khi đăng ký ảnh (blur, quá tối/sáng).
- Giảm false positive bằng threshold theo thực nghiệm.
- So sánh hiệu quả 1 ảnh vs nhiều ảnh/sinh viên.
- Thiết lập bộ dữ liệu test mini để regression test.

### Deliverables
- Báo cáo độ chính xác theo các kịch bản lớp học.
- Khuyến nghị cấu hình camera và môi trường ánh sáng.

---

## Phase 5 - Tối ưu vận hành (1-2 ngày)
### Mục tiêu
- Chạy mượt hơn trên máy demo.

### Việc cần làm
- Tối ưu chu kỳ quét frame.
- Giảm thời gian phản hồi API recognize.
- Tối ưu truy vấn attendance và export CSV.
- Rà soát logging để debug dễ hơn.

### Deliverables
- Phiên bản ổn định cho demo trực tiếp.

---

## Phase 6 - Đóng gói đồ án (1-2 ngày)
### Mục tiêu
- Sẵn sàng báo cáo và bảo vệ.

### Việc cần làm
- Cập nhật đầy đủ `README.md`, `frontend.md`, `database.md`.
- Hoàn thiện slide kiến trúc + workflow + kết quả test.
- Quay video demo theo kịch bản chuẩn.
- Chuẩn bị kịch bản fallback khi mất mạng/camera lỗi.

### Deliverables
- Bộ tài liệu hoàn chỉnh.
- Video demo.
- Checklist chạy demo 5-10 phút.

---

## Rủi ro chính và cách giảm thiểu
- Lệch phiên bản thư viện AI: khóa version trong `requirements.txt` và test sớm trên Python 3.10.11.
- Chất lượng camera/ánh sáng thấp: yêu cầu điều kiện tối thiểu trong tài liệu vận hành.
- Token/auth lỗi khi demo: chuẩn hóa xử lý 401 trên frontend.

## Cột mốc gợi ý (2 tuần)
- Tuần 1: Phase 0 -> 2.
- Tuần 2: Phase 3 -> 6.

## Định nghĩa hoàn thành (Definition of Done)
- Register/Recognize/Attendance chạy ổn với model thật.
- Frontend quản trị hoạt động đầy đủ.
- Có test cơ bản, tài liệu đầy đủ, demo trơn tru.