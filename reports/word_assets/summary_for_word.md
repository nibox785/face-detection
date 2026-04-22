# So lieu benchmark phuc vu bao cao

## 1. Threshold can bang an toan hon

- Threshold = 0.66
- F1 = 0.6490
- Accuracy = 0.6964
- Precision = 0.5622
- Recall = 0.7675
- False Accept (FP) = 162

### So sanh 0.61 va 0.66

| Chi so | 0.61 | 0.66 | Chenh lech |
|---|---:|---:|---:|
| Accuracy | 0.6707 | 0.6964 | +0.0256 |
| Precision | 0.5315 | 0.5622 | +0.0307 |
| Recall | 0.8413 | 0.7675 | -0.0738 |
| F1 | 0.6514 | 0.6490 | -0.0024 |
| FP | 201 | 162 | -39 |

- FP giam 19.40% khi chuyen tu 0.61 sang 0.66.

## 2. Latency so khop

- Loop per query = 0.745536 ms
- FAISS single per query = 0.063400 ms
- FAISS batch per query = 0.009827 ms
- Speedup single vs loop = 11.759x
- Speedup batch vs loop = 75.866x

## 3. Log ngan de dua vao bao cao

- Chon threshold = 0.66 vi can bang giua an toan va do nhay.
- FAISS giup rut ngan thoi gian tim kiem tu 0.745536 ms/xu ly xuong 0.063400 ms/xu ly.
- He thong luu ket qua qua API backend de tach loi AI khoi nghiep vu, de bao tri va mo rong.
