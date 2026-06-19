# Roadmap

Tóm tắt lộ trình refactor. **Source of truth cho phase:** `07-implementation.md`.

## Tóm tắt hiện trạng

- Backend: Python + FastAPI
- Frontend: React + Vite
- AI: DeepFace / RetinaFace / FaceNet512
- Search: FAISS
- DB: SQLite

Pipeline hiện tại:

```
Image → Detect (RetinaFace) → Embedding (FaceNet512) → FAISS → Decision → SQLite
```

## Các vấn đề chính

- `FaceService` gom quá nhiều nhiệm vụ AI.
- Business layer phụ thuộc trực tiếp DeepFace.
- Route vẫn gọi `db.py` trực tiếp; FAISS global trong `main.py`.
- **Đã cải thiện:** API tách domain routers (Phase A xong).

## Kiến trúc mục tiêu

```
React → FastAPI → Recognition Pipeline → Attendance Service → SQLite
```

Recognition Pipeline:

```
Frame → Detector → Recognizer → Search → Decision → Attendance
```

## Các phase (tóm tắt)

| Phase | Tên | Trạng thái |
|-------|-----|------------|
| 0 | Freeze current state | Largely done |
| A | Route separation | **Xong** |
| 1 | Recognition pipeline + clean architecture | Chưa |
| 2 | Configuration refactor | Chưa |
| 3 | Detector abstraction | Chưa |
| 4 | YOLOv11-face | Chưa |
| 5 | Recognizer + ArcFace | Chưa |
| 6 | ByteTrack | Chưa |
| 7 | Testing & benchmark | Một phần |

Chi tiết deliverable, checklist và module boundaries: `07-implementation.md`.

## Mục tiêu cuối cùng

```
YOLOv11-face → ByteTrack → ArcFace → FAISS → FastAPI → React
```

Đủ để thể hiện Computer Vision, Face Recognition, Backend API, Vector Search, System Design, Performance Optimization — phù hợp portfolio cá nhân, không over-engineering.

## Tài liệu liên quan

- `07-implementation.md` — kế hoạch refactor chi tiết
- `05-system-design.md` — nguyên tắc kiến trúc và phân lớp mục tiêu
- `06-ai-pipeline.md` — abstraction AI và migration model
- `dependency-analysis.md` — coupling hiện tại
