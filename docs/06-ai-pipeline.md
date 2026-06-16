# AI Pipeline

## Hiện tại

Pipeline hiện tại thực hiện các bước sau:

1. Nhận ảnh input từ frontend hoặc frame.
2. Detect face bằng RetinaFace (`face_engine/facenet/detect.py`).
3. Trích xuất embedding bằng FaceNet512 (`face_engine/facenet/embedding.py`).
4. Tùy chọn chạy liveness check.
5. Search trong database embeddings.
6. Trả về top-k kết quả và quyết định attendance.

## Components

### Detector

- Hiện tại: RetinaFace.
- Input: frame ảnh BGR.
- Output: list bounding boxes và face crops.
- Future: chuyển sang YOLOv11-face.

### Recognizer

- Hiện tại: FaceNet512.
- Input: face crop.
- Output: embedding vector 512-d.
- Future: ArcFace.

### Liveness

- Hiện tại gộp trong `get_embedding_with_liveness`. 
- Future nên tách thành module riêng.

### Search

- Hiện tại sử dụng FAISS hoặc loop cosine.
- Data: list của `(student_id, embedding)`.
- Future: sử dụng `IndexFlatIP` khi embedding đã normalize.

## Target pipeline

Frame
↓
Detector
↓
Recognizer
↓
Search Engine
↓
Decision Engine
↓
Attendance

## Proposed abstraction

### BaseDetector

```python
class BaseDetector:
    def detect(self, frame):
        raise NotImplementedError
```

### BaseRecognizer

```python
class BaseRecognizer:
    def embed(self, face_image):
        raise NotImplementedError
```

### BaseSearchEngine

```python
class BaseSearchEngine:
    def build(self, embeddings):
        raise NotImplementedError

    def search(self, query, top_k=1, threshold=0.7):
        raise NotImplementedError
```

## Example implementations

### RetinaFaceDetector

- Dùng DeepFace RetinaFace để detect.
- Xuất ra bounding boxes `{x, y, w, h, confidence}`.

### FaceNetRecognizer

- Dùng DeepFace FaceNet512.
- Trả về embedding chuẩn float32.

### FAISSEmbeddingIndex

- Build index với `dim=512`.
- Add embeddings incremental.
- Search top-k candidate.

## Refactor plan

### Phase 1

- Di chuyển AI logic xuống `face_engine/`.
- Giữ service layer gọi function hiện tại.

### Phase 2

- Thêm interface `BaseDetector`.
- Migrate `detect_faces` thành `RetinaFaceDetector.detect`.
- Config `DETECTOR=retinaface`.

### Phase 3

- Implement `YoloFaceDetector`.
- So sánh hiệu năng.

### Phase 4

- Thêm interface `BaseRecognizer`.
- Migrate FaceNet512 sang `FaceNetRecognizer`.
- Implement `ArcFaceRecognizer`.

### Phase 5

- Thêm track layer.
- Giảm embedding call trong realtime.

## Evaluation metrics

- Detection FPS.
- Recognition latency.
- Accuracy / top-k score.
- FAISS search time.
- Liveness false positive/negative rate.
