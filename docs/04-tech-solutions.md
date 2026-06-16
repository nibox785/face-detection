# Technical Solutions

## Technology stack

### Backend

- Python 3.10
- FastAPI
- Uvicorn
- SQLite cho data persistence
- JWT cho authentication
- slowapi tùy chọn cho rate limiting

### Frontend

- React 18
- Vite
- Fetch API + WebSocket

### AI / CV

- DeepFace cho detect/embedding hiện tại
- RetinaFace làm face detector hiện tại
- FaceNet512 làm face recognizer hiện tại
- Liveness gating tách riêng trong `face_engine`

### Search

- FAISS để tìm embedding tương tự nhanh
- IndexFlatL2 cho FaceNet512 hiện tại
- Dự kiến IndexFlatIP khi dùng ArcFace đã normalize

## Architectural patterns

- Clean Architecture: tách layers rõ ràng.
- Dependency inversion: business layer chỉ dùng interface.
- Strategy pattern: đổi detector/recognizer dễ dàng.
- Single responsibility: mỗi service chỉ một nhiệm vụ.

## Configuration

Môi trường cấu hình thông qua biến môi trường:

- `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_SECONDS`
- `MODEL_WARMUP_ENABLED`
- `DETECTOR`, `RECOGNIZER`
- `ALLOWED_ORIGINS`
- `SPOOF_*` thresholds

## Data storage strategy

- SQLite làm backend nhẹ, dễ triển khai.
- Embedding lưu dưới dạng binary `EMB1 + float32 bytes`.
- Lưu schema ổn định và hỗ trợ migration nhẹ.
- Revoke token lưu trong bảng `revoked_tokens`.

## Future migration roadmap

- Từ SQLite sang PostgreSQL khi cần production.
- Từ RetinaFace sang YOLOv11-face cho performance.
- Từ FaceNet512 sang ArcFace cho embedding tốt hơn.
- Thêm ByteTrack cho realtime tracking và giảm embedding calls.

## Justification

- FastAPI cho API nhẹ và scale moderate.
- React + Vite phù hợp demo giao diện nhanh.
- FAISS cung cấp vector search thể hiện hệ thống recognition.
- Tách AI module giảm coupling và giúp benchmark isolate.
