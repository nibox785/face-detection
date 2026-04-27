# Workflow

## 1) Luong van hanh he thong

1. Admin dang nhap (`/api/login`).
2. Dang ky sinh vien (uu tien luong 10 frame qua `/api/dataset/register-multiple`).
3. AttendancePanel bat dau phien realtime, gui frame dinh ky den `/api/recognize`.
4. Backend detect + liveness + recognize + decision.
5. Neu dat nguong, backend ghi attendance.
6. Frontend hien bbox, top-3 candidates, log diem danh.
7. Admin xem danh sach/lich su va export attendance.

## 2) Luong tao du lieu benchmark/bao cao

1. Chay phien diem danh trong AttendancePanel (2-5 phut).
2. Export `session_metrics_*.json` tu nut "Xuat JSON phien do".
3. Tao assets session:

```bash
python scripts/generate_session_report_assets.py --input reports/word_assets/session/session_metrics_latest.json
```

4. Chay benchmark nguong:

```bash
python scripts/benchmark_threshold.py --dataset dataset --start 0.30 --end 0.90 --step 0.01 --output benchmarks/threshold_report.json
```

5. Chay benchmark latency:

```bash
python scripts/benchmark_recognize_latency.py --embeddings 1000 --queries 1000 --output benchmarks/p2_latency.json
```

6. Chay benchmark liveness:

```bash
python scripts/benchmark_liveness_metrics.py --dataset dataset/liveness_eval
```

7. Tong hop markdown ket qua:

```bash
python scripts/generate_thesis_results_markdown.py --session-json reports/word_assets/session/session_metrics_latest.json
```

## 3) Dau ra bao cao thuong dung

- `reports/word_assets/chapter4_results.md`
- `benchmarks/p2_latency.json`
- `benchmarks/threshold_report.json`
- `benchmarks/liveness_report.json`
- `reports/word_assets/session/session_metrics_latest.json`

## 4) Tai lieu hoc nhanh cho van dap

- `docs/folder_guide_for_defense.md`