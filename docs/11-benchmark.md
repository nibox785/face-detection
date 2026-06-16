# Benchmark

## Mục tiêu benchmark

- Đo hiệu năng pipeline hiện tại.
- So sánh performance trước và sau refactor.
- Chứng minh lợi ích khi đổi detector/recognizer.

## Metrics cần đo

- Latency `POST /api/recognize`.
- Face detection FPS.
- Recognition latency.
- FAISS search time.
- End-to-end pipeline time.
- Tỷ lệ nhận diện chính xác nếu có ground truth.

## Existing benchmark assets

- `benchmarks/liveness_report.json`
- `benchmarks/p2_latency.json`
- `benchmarks/session_stability_report.json`
- `benchmarks/threshold_report.json`

## Benchmark scripts

- `scripts/benchmark_liveness_metrics.py`
- `scripts/benchmark_recognize_latency.py`
- `scripts/benchmark_session_stability.py`
- `scripts/benchmark_threshold.py`
- `scripts/comprehensive_face_recognition_benchmark.py`

## Baseline

### Current pipeline

- Detector: RetinaFace
- Recognizer: FaceNet512
- Search: FAISS IndexFlatL2

### Metrics to record

- `FPS_detect`
- `Latency_recognize`
- `Top1_accuracy`
- `Top3_accuracy`
- `FAISS_query_latency`

## Comparison table

| Pipeline | Detector | Recognizer | Search | Expected gain |
|----------|----------|------------|--------|---------------|
| Current | RetinaFace | FaceNet512 | FAISS L2 | baseline |
| Phase 3 | YOLOv11-face | FaceNet512 | FAISS L2 | +FPS |
| Phase 4 | YOLOv11-face | ArcFace | FAISS IP | +accuracy |
| Phase 5 | YOLO + ByteTrack | ArcFace | FAISS IP | +realtime |

## Benchmark process

1. Chạy `python scripts/benchmark_recognize_latency.py`.
2. Ghi kết quả trong `benchmarks/`.
3. So sánh trước và sau refactor.
4. Tạo báo cáo ngắn trong `docs/benchmark.md`.

## Notes

- Khi chuyển sang ArcFace, phải đổi search index sang `IndexFlatIP` nếu embedding đã normalize.
- So sánh FPS riêng cho detector và cho toàn bộ pipeline.
- Với ByteTrack, đo embedding calls/frame.

## Recommended benchmark outputs

- JSON report.
- Markdown summary.
- Biểu đồ đơn giản nếu cần.

## Validation criteria

- Pipeline mới phải ít nhất không chậm hơn baseline quá 20%.
- YOLO version phải tăng FPS đáng kể so với RetinaFace.
- ArcFace version phải giữ hoặc tăng accuracy.
- ByteTrack version phải giảm số lần embed calls trong realtime.
