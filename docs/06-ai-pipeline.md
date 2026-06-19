# AI Pipeline

Chi tiết abstraction và migration model. Phase refactor: `07-implementation.md` (source of truth).

## Hiện tại

Pipeline runtime trong `recognize_routes.py` + `face_service.py`:

1. Nhận ảnh/frame từ client.
2. Detect — RetinaFace (`face_engine/facenet/detect.py`).
3. Embed — FaceNet512 (`face_engine/facenet/embedding.py`).
4. Liveness — `get_embedding_with_liveness`.
5. Search — FAISS ưu tiên, fallback cosine loop.
6. Decision + top-3 candidates — ngưỡng trong `backend/api/common.py` (xem `08-api-design.md`).

## Components

### Detector

- Hiện tại: RetinaFace (BGR frame → bboxes + crops).
- Mục tiêu: YOLOv11-face qua `BaseDetector`.

### Recognizer

- Hiện tại: FaceNet512 (face crop → 512-d embedding).
- Mục tiêu: ArcFace qua `BaseRecognizer`.

### Liveness

- Hiện tại gộp trong `get_embedding_with_liveness`.
- Mục tiêu: module `liveness/` riêng trong `face_engine/`.

### Search

- Hiện tại: FAISS `IndexFlatL2` hoặc cosine loop.
- Mục tiêu: `IndexFlatIP` khi dùng embedding đã normalize (ArcFace).

## Target pipeline

```
Frame → Detector → Recognizer → Liveness → Search → Decision → Attendance
```

Entry point mục tiêu: `RecognitionPipeline` (`face_engine/pipeline/recognition_pipeline.py`).

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

- **RetinaFaceDetector** — DeepFace RetinaFace; output `{x, y, w, h, confidence}`.
- **FaceNetRecognizer** — DeepFace FaceNet512; float32 embedding.
- **FAISSEmbeddingIndex** — `dim=512`, incremental add, top-k search.

## Ánh xạ phase (theo `07-implementation.md`)

| Phase | Nội dung AI |
|-------|-------------|
| A ✅ | Tách API routers (không đổi pipeline) |
| 1 | `RecognitionPipeline`; di chuyển logic từ `facenet/*` |
| 2 | Config `DETECTOR`, `RECOGNIZER`, factory/registry |
| 3 | `BaseDetector` + `RetinaFaceDetector` |
| 4 | `YoloFaceDetector`; benchmark vs RetinaFace |
| 5 | `BaseRecognizer` + `FaceNetRecognizer` / `ArcFaceRecognizer` |
| 6 | ByteTrack — giảm embedding calls realtime |
| 7 | Benchmark FPS, latency, accuracy |

## Evaluation metrics

- Detection FPS
- Recognition latency
- Accuracy / top-k score
- FAISS search time
- Liveness false positive/negative rate

Chi tiết scripts và baseline: `11-benchmark.md`.
