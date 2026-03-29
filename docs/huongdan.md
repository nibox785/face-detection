# 👥 Hướng dẫn làm việc nhóm (Team Workflow)

## 🌳 Chiến lược branch

- main: code ổn định, dùng để demo
- develop: nhánh phát triển chính
- feature/*: nhánh cho từng chức năng

---

## 🔄 Quy trình làm việc

1. Cập nhật code mới nhất:
   git checkout develop
   git pull origin develop

2. Tạo branch mới:
   git checkout -b feature/<ten-chuc-nang>

3. Code chức năng

4. Commit:
   git commit -m "feat: mô tả chức năng"

5. Push:
   git push origin feature/<ten-chuc-nang>

6. Tạo Pull Request → merge vào develop

---

## 🚫 Quy tắc

- Không commit trực tiếp vào main
- Không push code lỗi
- Code phải chạy được trước khi merge

---

## 🔍 Review code

- Phải có ít nhất 1 người review trước khi merge
- Kiểm tra:
  - Code chạy được
  - Logic đúng
  - Code sạch, dễ đọc

---

## 📝 Quy tắc đặt tên

- Python: snake_case
- Biến phải rõ nghĩa

---

## 🔥 Quy tắc commit

- feat: thêm tính năng
- fix: sửa lỗi
- docs: tài liệu
- chore: cấu hình

---

## ⚠️ Lưu ý quan trọng

- Luôn pull code trước khi làm
- Tránh xung đột (conflict)