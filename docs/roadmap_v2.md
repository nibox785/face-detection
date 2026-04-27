# 🚀 Roadmap V2 - Face Attendance System

## Mục tiêu tổng quan
- Chuyển từ bản prototype (mock AI) sang hệ thống nhận diện thật với DeepFace (RetinaFace + Facenet512).
- Ổn định backend, chuẩn hóa frontend và hoàn thiện demo đồ án.

## Sprint ưu tiên theo mức độ nghiêm trọng

### Sprint P0 - An toàn vận hành và nhất quán dữ liệu (cao nhất, làm trước)
Mục tiêu:
- Tránh lỗi gây gián đoạn vận hành và giảm rủi ro dữ liệu/auth.

Trạng thái:
- ✅ Đã triển khai.

Phạm vi:
- Chuẩn hóa toàn bộ truy cập SQLite qua lớp database chung, không mở kết nối trực tiếp trong route.
- Chuyển blacklist token từ in-memory sang lưu bền (SQLite) để logout không mất hiệu lực khi restart.
- Hoàn tất cleanup delete flow chỉ dựa trên foreign key cascade, kiểm tra toàn bộ endpoint liên quan.

Kết quả triển khai:
- Routes quản trị đã bỏ cập nhật SQLite trực tiếp, dùng hàm database chung.
- Revoked token được lưu bền trong bảng `revoked_tokens` và có cơ chế dọn token hết hạn.
- Luồng xóa sinh viên tiếp tục dựa trên `ON DELETE CASCADE` với `PRAGMA foreign_keys = ON`.

Điều kiện hoàn thành:
- Không còn thao tác SQLite trực tiếp trong API route chính.
- Logout vẫn có hiệu lực sau khi restart backend.
- Bộ test xóa sinh viên xác nhận attendance/embeddings được xóa đúng qua cascade.

---

### Sprint P1 - Chất lượng API và độ tin cậy kiểm thử
Mục tiêu:
- Giảm regression khi thay đổi logic nhận diện/đăng ký.

Trạng thái:
- 🔄 Đang triển khai.

Phạm vi:
- Bổ sung test API cho login, auth verify, register, recognize, delete student.
- Bổ sung test migration embedding (blob nhị phân mới + dữ liệu pickle cũ).
- Thiết lập test dependency và lệnh chạy test chuẩn cho team.

Tiến độ hiện tại:
- ✅ Đã thêm test API core cho auth/login/logout, register (stub), recognize (stub), update/delete student.
- ✅ Đã mở rộng test nhánh lỗi quan trọng: login sai mật khẩu, thiếu Bearer token, header auth sai format, file không phải ảnh, MSSV trùng.
- ✅ Đã bổ sung test cho endpoint rủi ro cao: `dataset/register-multiple` (success + insufficient images) và `face/liveness-check` (success + no-face).
- ✅ Đã thêm test tương thích embedding cho format mới và dữ liệu pickle cũ.
- ✅ Đã thêm `requirements-dev.txt` cho môi trường test.
- ✅ Đã giảm warning deprecation từ test client bằng cách ghim `httpx==0.26.0` trong môi trường test.

Điều kiện hoàn thành:
- Test backend mức core chạy pass trong môi trường chuẩn.
- Tối thiểu có coverage cho các endpoint quan trọng và backward compatibility.

---

### Sprint P2 - Hiệu năng và chất lượng nhận diện
Mục tiêu:
- Tăng tốc nhận diện và ổn định độ chính xác khi demo thực tế.

Trạng thái:
- 🔄 Đang triển khai.

Phạm vi:
- Tối ưu batch FAISS thực sự cho nhiều query cùng lúc.
- Warm-up model detect/embedding khi startup để giảm latency request đầu.
- Chuẩn hóa benchmark threshold và theo dõi false positive/false negative.

Tiến độ hiện tại:
- ✅ Đã tối ưu `search_batch` để dùng truy vấn FAISS theo lô (không lặp từng query như trước).
- ✅ Đã bổ sung warm-up model detect/embedding khi startup, có cờ `MODEL_WARMUP_ENABLED` và tự skip khi chạy test.
- ✅ Đã bổ sung script benchmark độ trễ recognize before/after: loop vs FAISS single vs FAISS batch.
- ✅ Đã nâng cấp script benchmark threshold để xuất báo cáo JSON và top-5 threshold.
- ✅ Đã chạy benchmark P2 và lưu báo cáo:
	- `benchmarks/p2_latency.json`: FAISS single nhanh hơn loop ~11.76x, FAISS batch nhanh hơn loop ~75.87x.
	- `benchmarks/threshold_report.json`: threshold tốt nhất theo F1 là 0.61; threshold cân bằng an toàn hơn cho vận hành đề xuất là 0.66.
- 🔄 Cần mở rộng dataset (hiện chỉ 3 students hợp lệ) để hiệu chỉnh threshold ổn định hơn trước khi chốt production.

Điều kiện hoàn thành:
- Thời gian phản hồi recognize ổn định hơn ở tải demo.
- Có báo cáo benchmark trước/sau và ngưỡng được ghi nhận rõ trong tài liệu.

## Phase 0 - Đánh giá hiện trạng (1-2 ngày)
### Mục tiêu
- Chốt những phần đã xong và phần còn thiếu.

### Ưu tiên hotfix hiện tại
- Sửa `/health` để không crash do import `datetime` sai.
- Tái sử dụng FAISS index dùng chung thay vì build lại mỗi request.
- Ưu tiên nhận diện/đăng ký theo MSSV để tránh trùng tên.

### Việc cần làm
- Rà soát toàn bộ API đang dùng ở frontend/backend.
- Xác nhận schema database cuối cùng (`students`, `embeddings`, `attendance`).
- Ghi rõ phần nào đang là mock AI để tránh nhầm với production.

### Deliverables
- Tài liệu trạng thái hệ thống hiện hành.
- Danh sách issue ưu tiên theo mức độ ảnh hưởng.

---

## Phase 1 - AI Core thật (DeepFace RetinaFace + Facenet512) (3-5 ngày)
### Mục tiêu
- Thay hoàn toàn mock detect/embedding bằng model thật.

### Việc cần làm
- Tích hợp RetinaFace (qua DeepFace) cho detect khuôn mặt.
- Tích hợp Facenet512 (qua DeepFace) để trích xuất embedding 512-d.
- Chuẩn hóa tiền xử lý ảnh (crop, resize, normalize).
- Thiết lập ngưỡng similarity ban đầu (threshold tuning).

### Deliverables
- `detect.py` chạy detect thật voi RetinaFace.
- `embedding.py` chạy embedding thật voi Facenet512.
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
- Bổ sung unit test cho `_safe_bbox()` và các edge case bbox sát biên ảnh.
- Hoàn thiện migration dữ liệu embedding sang format nhị phân mới và theo dõi backward compatibility.
- Dọn các luồng xóa dữ liệu để chỉ giữ một nguồn sự thật là cascade theo foreign key.

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
- Tuần 1: Sprint P0 -> P1 (song song hoàn thiện Phase 2).
- Tuần 2: Sprint P2 + Phase 3 -> 6.

## Định nghĩa hoàn thành (Definition of Done)
- Register/Recognize/Attendance chạy ổn với model thật.
- Frontend quản trị hoạt động đầy đủ.
- Có test cơ bản, tài liệu đầy đủ, demo trơn tru.