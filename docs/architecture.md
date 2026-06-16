# System Architecture

# Design Principles

The system follows several architectural principles:

## Separation of Concerns

Responsibilities are separated into:

- API Layer
- Service Layer
- AI Engine Layer
- Database Layer

Each layer only communicates with adjacent layers.

---

## Single Responsibility Principle

Each service should focus on one business capability.

Examples:

- AttendanceService
- RegisterService
- FaceService

---

## AI Pipeline Isolation

AI models are isolated from business logic.

Future model replacements:

RetinaFace → YOLOv11-face

FaceNet512 → ArcFace

should not affect API contracts.

---

## Extensibility

Detector and Recognizer components should be replaceable through interfaces.

# Architecture Evolution

## Current

Client
↓
FastAPI
↓
FaceService
↓
RetinaFace
↓
FaceNet512
↓
FAISS
↓
SQLite

---

## Target

Client
↓
FastAPI
↓
RecognitionPipeline
├── Detector
├── Recognizer
├── Search
└── Liveness
↓
Attendance Service
↓
SQLite

## 1) Layers

1. Frontend (React/Vite)
2. Backend API (FastAPI)
3. Service layer (`face_service`, `register_service`, `attendance_service`, `faiss_search`)
4. Face engine wrapper (`face_engine/facenet`)
5. SQLite database (`attendance.db`)

## 2) Runtime flow

Frontend camera frame
-> `/api/recognize`
-> detect face (RetinaFace)
-> embedding + liveness (Facenet512)
-> FAISS/cosine search
-> decision + attendance write
-> response (bbox, top-3, decision)

## 3) Startup flow

`backend/main.py` lifespan:

1. `init_db()`
2. `update_embeddings_cache()`
3. `init_faiss_index()`
4. `warmup_ai_models()` (co the disable qua env)

## 4) Security model

- Admin auth bang JWT (`/api/login`).
- Token revoke bang `revoked_tokens` table (`/api/logout`).
- Endpoint quan tri va recognize deu can Bearer token hop le.

## 5) Data model tom tat

- `students` (identity + MSSV)
- `embeddings` (vector)
- `attendance` (log theo timestamp)
- `revoked_tokens` (token blacklist ben vung)