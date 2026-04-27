# Folder Guide For Defense

## 1) Muc tieu tai lieu

Tai lieu nay giup thanh vien nhom:

1. Hieu ro y nghia tung folder trong du an.
2. Biet file nao la trong tam khi giai thich voi hoi dong.
3. Co script tra loi nhanh cho cac cau hoi van dap ve code.

## 2) Toan canh he thong theo folder

1. `frontend/`: Giao dien web cho admin (dang nhap, dang ky, diem danh realtime, quan ly).
2. `backend/`: API FastAPI + nghiep vu xu ly attendace va nhan dien.
3. `face_engine/`: Lop wrapper AI (detect, embedding, liveness) tach rieng khoi business API.
4. `dataset/`: Du lieu anh dang ky va bo du lieu danh gia (threshold, liveness, benchmark).
5. `benchmarks/`: Ket qua do luong dung de bao cao (latency, threshold, liveness).
6. `scripts/`: Cong cu chay benchmark, tao report, tien xu ly du lieu.
7. `tests/`: Test API va test core module de tranh regression.
8. `docs/`: Tai lieu kien truc, workflow, roadmap, migration.
9. `core/`: Cau hinh chung (secret, token expire, env).
10. `backend/database/`: Truy cap SQLite, schema, model du lieu.

## 3) Giai thich chi tiet theo module

### 3.1 `backend/`

1. `backend/main.py`
   - Diem vao backend.
   - Khoi tao DB, cache embedding, FAISS index, warmup model.
   - Mount router voi prefix `/api` (quan trong de giai thich duong dan WS: `/api/ws/...`).
2. `backend/api/routes.py`
   - Dinh nghia endpoint.
   - Noi ghep day du detect -> liveness -> recognize -> decision -> attendance write.
   - Co WebSocket realtime:
     - `/api/ws/recognize` (mode cu: FE gui frame + track_hints, backend detect va gan track_id theo hints).
     - `/api/ws/realtime/{session_id}` (mode hien tai: FE gui frame, backend detect + track + tra bbox + track_id + result).
3. `backend/services/face_service.py`
   - Facade cho detect, embedding, liveness, recognize.
   - Gom logic cosine va goi FAISS.
4. `backend/services/faiss_search.py`
   - Quan ly FAISS index de tang toc tra cuu embedding.
5. `backend/services/register_service.py`
   - Nghiep vu dang ky student tu 1 frame/nhieu frame.
6. `backend/services/attendance_service.py`
   - Nghiep vu ghi diem danh va truy van lich su.

### 3.2 `face_engine/`

1. `face_engine/facenet/detect.py`
   - Detect khuon mat bang DeepFace + RetinaFace.
   - Chuan hoa bbox va loc confidence.
2. `face_engine/facenet/embedding.py`
   - Trich xuat embedding Facenet512.
   - Chay liveness anti-spoof va tra ve `(embedding, is_real, spoof_score)`.
   - Da co huong fail-closed neu liveness loi/khong du truong.

### 3.3 `backend/database/`

1. `db.py`: CRUD + truy van SQLite, nguon su that cho du lieu.
2. `models.py`: Cau truc bang va mapping.
3. `schemas.py`: Response model de API on dinh va ro rang.

### 3.4 `frontend/src/`

1. `components/features/AttendancePanel.jsx`
   - Loop gui frame qua WebSocket `/api/ws/realtime/{session_id}`.
   - Backend tra `tracks[]` (bbox + track_id + result). FE ve overlay theo `tracks[]` va giu track mot khoang thoi gian de tranh nhap nhay.
   - Co fallback HTTP `/api/recognize` khi WS chua san sang.
   - Telemetry realtime: FPS overlay, API calls/phut, latency gan nhat/trung binh, decision counters.
2. `components/features/RegisterPanel.jsx`
   - Dang ky du lieu student.
3. `components/features/LoginPanel.jsx`
   - Dang nhap admin, luu token.
4. `components/features/StudentsPanel.jsx`
   - Quan ly danh sach sinh vien va lich su.
5. `api/apiClient.js`
   - Cau hinh goi API va auth header.
   - Build WS URL dung prefix `/api` (vi router FastAPI mount voi prefix `/api`).
6. `context/AuthContext.jsx`
   - Quan ly trang thai phien dang nhap tren frontend.

### 3.5 `scripts/`

1. `benchmark_recognize_latency.py`: So sanh loop vs FAISS.
2. `benchmark_threshold.py`: Sweep threshold cho recognize.
3. `benchmark_liveness_metrics.py`: Tinh APCER/BPCER/ACER cho liveness.
4. `generate_thesis_results_markdown.py`: Tong hop markdown phuc vu bao cao.

### 3.6 `tests/`

1. `test_api_core.py`: Test endpoint chinh (auth, register, recognize, liveness).
2. `test_detect_bbox.py`: Test bbox edge case.
3. `test_embedding_compat.py`: Test tuong thich du lieu embedding cu/moi.
4. `test_faiss.py`: Test chi tiet module FAISS.

## 4) Luong code can thuoc de van dap

### 4.1 Realtime attendance (luong hien tai)

- FE -> WebSocket `/api/ws/realtime/{session_id}?token=...`
  - FE gui `{"type":"frame","image": "data:image/jpeg;base64,...", "frame_id": "..."}`
  - Backend:
    - Update tracker nhanh moi frame (MOSSE/KCF trong OpenCV) de giu bbox lien tuc.
    - Chay detect nang theo chu ky (de refresh tracker, bat mat moi).
    - (Throttle) recognize theo track: liveness + embedding + FAISS/cosine + decision + ghi attendance.
  - Backend tra `{"type":"frame_result","tracks":[{track_id,bbox,result}]}`
- FE:
  - Ve bbox theo `tracks[]` (overlay loop 20-30 FPS).
  - Cap nhat label/decision theo `result` neu co.

### 4.2 Register multi-frame (diem de noi khi hoi dong hoi "tai sao can 10 frame?")

- FE -> `/api/dataset/register-multiple`
- Backend:
  - Cham diem chat luong frame (do net, do sang, ty le khuon mat, vi tri, confidence).
  - Chon frame tot + fallback neu loc qua chat.
  - Luu embedding + luu anh dataset + reload cache + rebuild FAISS.

### 4.3 Benchmark & phan tich du lieu

- Threshold sweep: `scripts/benchmark_threshold.py` -> `benchmarks/threshold_report.json`
- Latency loop vs FAISS: `scripts/benchmark_recognize_latency.py` -> `benchmarks/p2_latency.json`
- Liveness metrics (APCER/BPCER/ACER): `scripts/benchmark_liveness_metrics.py` -> `benchmarks/liveness_report.json`
- Telemetry session tu UI: export JSON/Excel (phuc vu minh hoa trade-off CPU-only).

## 5) Diem manh / diem yeu (noi thang, de de ghi diem khi van dap)

### 5.1 Diem manh

1. **End-to-end workflow ro rang**: auth -> register -> realtime attendance -> persist DB -> export.
2. **Liveness gate 2 tang + adaptive leniency**:
   - Hard reject khi spoof_score rat cao.
   - "Suspect" (khong reject ngay) de giam false reject dot ngot luc bat dau session / goc nhin xau.
   - Adaptive threshold theo ty le khuon mat (nguoi dung dung gan camera).
3. **Scale tim kiem embedding**: cache embeddings + FAISS index (fallback loop cosine).
4. **Quan tri du lieu dang ky**: 10-frame + quality scoring + fallback -> giam noise vao DB.
5. **Do luong duoc**: co benchmark scripts + telemetry export (latency, FPS, API calls/min, decision stats).

### 5.2 Diem yeu / han che hien tai (CPU-only)

1. **Compute nang**: DeepFace (RetinaFace + Facenet512) + liveness + FAISS -> tren CPU latency cao, FPS WS thuc te thap.
2. **Transport WS dang gui JPEG base64**: co overhead encode/decode + base64 (khong giong he thong cong nghiep ingest RTSP).
3. **Tracking MOSSE/KCF chi la giai phap "lightweight"**:
   - Tot de giu bbox lien tuc, nhung chua manh nhu ByteTrack/DeepSORT khi nhieu doi tuong/occlusion.
4. **TensorFlow tren Windows khong an CUDA GPU** (tf 2.12 -> `GPU == []`), neu muon GPU can WSL2.

## 6) Huong phat trien (noi "neu co them thoi gian/nguon luc")

1. **Muc tieu mượt**: doi transport sang WebRTC/RTSP ingest (giam base64) + resize frame server-side.
2. **Tracking production**: thay MOSSE/KCF bang ByteTrack + detector YOLO (neu bai toan mo rong multi-face/multi-cam).
3. **GPU enable**: chay backend trong WSL2 + CUDA (`docs/gpu_wsl2.md`) de tang throughput.
4. **Edge deployment**: OpenVINO/ONNX Runtime (CPU/NPU) neu muon chay tren may yeu.
5. **Mo rong dataset liveness**: tang do phu (anh, video replay, mask) -> chot threshold production.

## 7) Vai tro goi y cho nhom 4-5 thanh vien

1. Thanh vien A (Backend/API): Endpoint, auth JWT, error handling.
2. Thanh vien B (AI pipeline): detect + embedding + liveness + threshold.
3. Thanh vien C (Data/Benchmark): dataset policy, APCER/BPCER/ACER, report.
4. Thanh vien D (Frontend): luong UI, camera loop, auth context.
5. Thanh vien E (DB/Test/DevOps nhe): schema, migration, unit/API tests, runbook demo.

## 8) Cau hoi hoi dong hay gap va cach tra loi ngan

1. "Diem moi cua de tai so voi demo tren mang la gi?"
   - Tra loi: khong chi nhan dien, ma co full workflow nghiep vu + do luong (telemetry/benchmark) + chong spoof (liveness) + policy decision + scale (FAISS).

2. "Tai sao dung FAISS?"
   - Tra loi: de scale tim kiem embedding nhanh hon loop cosine khi so sinh vien tang.

3. "Liveness hien tai da production chua?"
   - Tra loi: chua, nhom da co pipeline + benchmark APCER/BPCER/ACER, nhung dataset liveness hien tai con nho nen can mo rong de chot threshold production.

4. "Neu AI fail thi he thong xu ly sao?"
   - Tra loi: co fail-closed cho liveness va co decision manual review/reject de giam rui ro false acceptance.

5. "Lam sao dam bao tin cay code?"
   - Tra loi: co bo test API/core + benchmark script + docs workflow de lap lai ket qua.

## 9) Checklist chuan bi truoc ngay bao ve

1. Chay test: `pytest tests/test_api_core.py -q`.
2. Chay benchmark: latency + threshold + liveness.
3. Chuan bi 1-2 case demo that bai co chu y (vd spoof bi reject, frame xau bi manual review).
4. Moi thanh vien thuoc 1 luong end-to-end va 1 module sau.
