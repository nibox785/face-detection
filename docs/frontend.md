# 💻 Frontend

## Mục tiêu frontend
Frontend là giao diện quản lý cho hệ thống điểm danh khuôn mặt, bao gồm:
- Đăng nhập admin
- Đăng ký sinh viên với ảnh/camera
- Điểm danh tự động bằng webcam
- Xem danh sách sinh viên
- Xem lịch sử điểm danh
- Xuất báo cáo CSV
- Xóa và sửa thông tin sinh viên

## Công nghệ chính
- React 18
- Vite
- HTML/CSS cho giao diện
- Fetch API để kết nối với backend FastAPI

## Cấu trúc thư mục
`frontend/`
- `package.json` - cấu hình dự án React/Vite
- `index.html` - điểm vào ứng dụng
- `src/`
  - `main.jsx` - render React app và bọc `AuthProvider`
  - `App.jsx` - điều hướng tab và hiển thị các panel chính
  - `styles.css` - style toàn cục
  - `context/AuthContext.jsx` - quản lý authentication token và trạng thái đăng nhập
  - `api/apiClient.js` - helper gửi request tới backend và thêm `Authorization` header
  - `components/features/`
    - `LoginPanel.jsx` - form đăng nhập admin
    - `RegisterPanel.jsx` - form đăng ký sinh viên, chụp ảnh bằng camera và gửi ảnh lên backend
    - `AttendancePanel.jsx` - điểm danh tự động bằng webcam, hiển thị log và xuất CSV
    - `StudentsPanel.jsx` - hiển thị danh sách sinh viên, chỉnh sửa tên, xóa sinh viên và lịch sử điểm danh

## Luồng chính
1. Người dùng mở ứng dụng.
2. `AuthProvider` đọc token từ `localStorage`.
3. Nếu chưa đăng nhập, hiển thị `LoginPanel`.
4. Sau khi đăng nhập thành công, app chuyển đến giao diện chính.
5. Người dùng chọn tab:
   - `Đăng ký`: dùng `RegisterPanel` để gửi ảnh đăng ký sinh viên lên `/api/dataset/register`.
   - `Điểm danh`: dùng `AttendancePanel` để mở camera và gửi ảnh đến `/api/recognize` định kỳ.
   - `Danh sách`: dùng `StudentsPanel` để xem sinh viên, lịch sử điểm danh, sửa tên và xóa sinh viên.

## Chi tiết các file quan trọng
### `src/main.jsx`
- Render `App` vào `#root`.
- Bọc app bằng `AuthProvider` để cung cấp auth state toàn cục.

### `src/App.jsx`
- Quản lý tab UI.
- Tải dữ liệu sinh viên và điểm danh khi chọn tab `students`.
- Hiển thị `LoginPanel` nếu chưa auth.
- Gọi `logout()` tại nút đăng xuất.

### `src/context/AuthContext.jsx`
- Lưu token trong `localStorage` với `setToken` / `clearToken`.
- Cung cấp `isAuthenticated`, `login`, `logout`, `isLoading`.

### `src/api/apiClient.js`
- `API_BASE` trỏ đến `http://127.0.0.1:8000/api`.
- `authHeaders()` thêm header `Authorization: Bearer <token>`.
- `apiFetch()` gửi request và xử lý lỗi 401 tự động.

### `src/components/features/LoginPanel.jsx`
- Gửi request POST `/login`.
- Lưu token lên context khi đăng nhập thành công.

### `src/components/features/RegisterPanel.jsx`
- Mở camera, chụp ảnh và tạo `FormData`.
- Gọi `apiFetch('/dataset/register', { method: 'POST', body: formData })`.
- Reset form và gọi `onRegisterSuccess` khi thành công.

### `src/components/features/AttendancePanel.jsx`
- Mở webcam, chụp ảnh và gửi định kỳ lên `/recognize`.
- Hiển thị log trạng thái, kết quả nhận diện, và lỗi.
- Cho phép xuất CSV từ `/attendance/export`.

### `src/components/features/StudentsPanel.jsx`
- Hiển thị danh sách sinh viên và lịch sử điểm danh.
- Tạo modal chỉnh sửa tên.
- Gọi API `PUT /students/{id}` để cập nhật tên và `DELETE /students/{id}` để xóa.


## Đề xuất mở rộng
- Đồng bộ trạng thái xóa/sửa với `students` và `attendance` ngay tức thì.
