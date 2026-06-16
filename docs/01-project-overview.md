# Project Overview

## Mục tiêu dự án

Face Recognition Attendance System là một project cá nhân nhằm:

- Thể hiện năng lực AI Engineer / Computer Vision Engineer.
- Xây dựng backend FastAPI với pipeline nhận diện khuôn mặt.
- Minh họa vector search bằng FAISS và hệ thống attendance.
- Giữ trải nghiệm người dùng đơn giản, rõ ràng và hiệu quả.

### Người dùng chính

- Giáo viên / giảng viên: đăng nhập, điểm danh, xem kết quả.
- Quản trị viên: quản lý sinh viên, đăng ký khuôn mặt, kiểm tra hệ thống.
- Sinh viên: đăng ký khuôn mặt và tham gia điểm danh.

## Phạm vi

### In scope

- API nhận diện và đăng ký khuôn mặt.
- Quản lý sinh viên và attendance.
- Search embedding bằng FAISS.
- Giao diện React đơn giản để minh hoạ.
- Refactor theo kiến trúc clean, tách AI pipeline khỏi business layer.

### Out of scope

- Hệ thống microservice production-grade.
- Multi-tenant hoặc một hệ thống quy mô lớn.
- Triển khai cloud tích hợp sẵn.
- Hệ thống nhận diện khuôn mặt cho nhiều camera phức tạp.

## Current state

- Backend FastAPI, frontend React + Vite.
- AI pipeline dùng DeepFace/RetinaFace/FaceNet512.
- FAISS để search embedding.
- SQLite lưu students, embeddings, attendance, token.

## Target state

- Modular pipeline gồm:
  - Detector
  - Recognizer
  - Search engine
  - Attendance decision
- Tách business logic khỏi model cụ thể.
- Cho phép thay detector/recognizer mà không đổi API.
- Giữ API contracts ổn định.
- Thêm benchmark, testing, và báo cáo.

## Kết quả mong đợi

- Độ ổn định tốt hơn khi thay đổi model.
- Dễ bảo trì và mở rộng.
- Có baseline performance để so sánh.
- Có tài liệu rõ ràng cho từng bước refactor.
