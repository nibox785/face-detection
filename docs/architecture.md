# System Architecture

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