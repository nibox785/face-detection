# Chuong 4 - Ket qua thuc nghiem

## 4.1 Cau hinh va du lieu

- So luong danh tinh benchmark threshold: 3
- So cap positive: 271
- So cap negative: 470
- Kich thuoc embedding: 512

## 4.2 Ket qua toi uu nguong nhan dien

- Best threshold: 0.61
- Accuracy: 0.6707
- Precision: 0.5315
- Recall: 0.8413
- F1-score: 0.6514
- Confusion: TP=228, FP=201, TN=269, FN=43

Bang top-5 threshold co the trinh bay trong phu luc:
- t=0.61 | Acc=0.6707 | P=0.5315 | R=0.8413 | F1=0.6514
- t=0.60 | Acc=0.6653 | P=0.5263 | R=0.8487 | F1=0.6497
- t=0.66 | Acc=0.6964 | P=0.5622 | R=0.7675 | F1=0.6490
- t=0.64 | Acc=0.6856 | P=0.5485 | R=0.7934 | F1=0.6486
- t=0.63 | Acc=0.6788 | P=0.5407 | R=0.8081 | F1=0.6479

Hinh de chen:
- reports/word_assets/threshold_061_vs_066.png
- reports/word_assets/threshold_top5_curve.png

## 4.3 Ket qua toc do nhan dien (latency)

- Loop baseline: 0.745536 ms/query
- FAISS single: 0.063400 ms/query
- FAISS batch: 0.009827 ms/query
- Speedup single vs loop: 11.759x
- Speedup batch vs loop: 75.866x

Hinh de chen:
- reports/word_assets/latency_comparison.png

## 4.4 Ket qua telemetry theo phien

- Session started at: 2026-04-26T19:45:19.875Z
- Recognition interval: 700 ms
- So mau latency: 40
- Latency trung binh phien: 1844.32 ms
- Latency p95 phien: 1886.10 ms
- AUTO_MARK: 24 (60.00%)
- MANUAL_REVIEW: 14 (35.00%)
- REJECT: 2 (5.00%)

Hinh de chen:
- reports/word_assets/session/session_latency_timeline.png
- reports/word_assets/session/session_fps_api_timeline.png
- reports/word_assets/session/session_decision_ratio.png

## 4.5 Chi so anti-spoofing (APCER, BPCER, ACER)

- Chua co liveness_report.json. Hay chay benchmark_liveness_metrics.py de bo sung APCER/BPCER/ACER.

## 4.6 Do on dinh qua nhieu phien (mean +- std)

- So phien duoc benchmark: 1
- FPS mean +- std: 80.120 +- 0.000
- API calls/min mean +- std: 18.916 +- 0.000
- Latency mean (ms) mean +- std: 1844.322 +- 0.000
- Latency p95 (ms) mean +- std: 1886.100 +- 0.000
- AUTO_MARK ratio mean +- std: 60.00% +- 0.00%
- MANUAL_REVIEW ratio mean +- std: 35.00% +- 0.00%
- REJECT ratio mean +- std: 5.00% +- 0.00%

Hinh de chen:
- reports/word_assets/session/session_stability_errorbars.png

## 4.7 Tong hop dong gop ky thuat

- He thong ket hop detect + embedding + liveness gate trong mot luong suy dien thong nhat.
- Co che tim kiem FAISS giup cai thien ro rang ve latency so voi loop baseline.
- Giao dien telemetry va top-3 confidence tang kha nang giai thich quyet dinh nhan dien.
- Quy trinh sinh report duoc tu dong hoa de su dung lai cho cac lan benchmark tiep theo.

## 4.8 Ban luan va han che

- Du lieu threshold hien tai con nho, can mo rong danh tinh va dieu kien moi truong.
- Can benchmark nhieu phien va bao cao do lech chuan de ket luan on dinh hon.

## 4.9 Trich doan session summary

Noi dung duoi day duoc trich tu file session summary:

# Tong hop phien telemetry cho bao cao

## 1. Thong tin phien

- Started at: 2026-04-26T19:45:19.875Z
- Exported at: 2026-04-26T19:46:49.711Z
- Recognition interval (ms): 700
- So moc telemetry: 83
- So su kien recognize: 42

## 2. Chi so hieu nang

- FPS trung binh: 80.12
- API calls/phut trung binh: 18.92
- Latency trung binh: 1844.32 ms
- Latency p95: 1886.10 ms
- Face count trung binh/event: 0.95
- Recognized count trung binh/event: 0.74

## 3. Phan bo quyet dinh

- AUTO_MARK: 24 (60.00%)
- MANUAL_REVIEW: 14 (35.00%)
- REJECT: 2 (5.00%)

## 4. Nhan xet nhanh

- Neu MANUAL_REVIEW cao: can canh chinh threshold hoac cai thien chat luong anh dau vao.
- Neu REJECT cao: kiem tra liveness threshold va dieu kien camera/anh sang.
- So sanh latency p95 giua cac phien de theo doi on dinh he thong.
