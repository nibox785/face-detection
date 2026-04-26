# 🔄 Luồng hoạt động hệ thống

1. Camera chụp ảnh
2. Phát hiện khuôn mặt
3. Trích xuất embedding
4. So sánh với database
5. Nhận diện sinh viên
6. Lưu điểm danh

## 📊 Workflow tạo dữ liệu báo cáo tiểu luận

1. Chạy phiên điểm danh trong giao diện Attendance (2-5 phút).
2. Bấm `Xuất JSON phiên đo` để tải file `session_metrics_*.json`.
3. Sinh chart cho Word từ session JSON:

```bash
python scripts/generate_session_report_assets.py --input reports/word_assets/session/session_metrics_latest.json
```

4. Sinh markdown Chương 4 (gộp benchmark + session):

```bash
python scripts/generate_thesis_results_markdown.py --session-json reports/word_assets/session/session_metrics_latest.json
```

5. Benchmark liveness metrics chuẩn (APCER/BPCER/ACER):

```bash
python scripts/benchmark_liveness_metrics.py --dataset dataset/liveness_eval
```

6. Benchmark độ ổn định nhiều phiên (mean +- std):

```bash
python scripts/benchmark_session_stability.py --input-glob "reports/word_assets/session/session_metrics_*.json"
```

7. Sinh lại Chương 4 sau khi có đủ các report:

```bash
python scripts/generate_thesis_results_markdown.py --session-json reports/word_assets/session/session_metrics_latest.json
```

5. Chèn các file sau vào Word:
- `reports/word_assets/chapter4_results.md`
- `reports/word_assets/threshold_061_vs_066.png`
- `reports/word_assets/threshold_top5_curve.png`
- `reports/word_assets/latency_comparison.png`
- `reports/word_assets/session/session_latency_timeline.png`
- `reports/word_assets/session/session_fps_api_timeline.png`
- `reports/word_assets/session/session_decision_ratio.png`