> **Deprecated (2026-06):** Tài liệu legacy trước khi tách domain routers. Tham khảo `07-implementation.md`, `05-system-design.md`, `dependency-analysis.md` thay thế.

# Blueprint Migrate Nghiep Vu Tu Attendance-by-Face

Ngay cap nhat: 2026-04-27

## 0) Hiểu rõ hệ thống - Cấu trúc và logic quan trọng

### 0.1 Cấu trúc folder và file quan trọng

- **backend/**: Chứa code backend FastAPI.
  - `main.py`: Entry point server.
  - `api/routes.py`: Định nghĩa API endpoints (register, recognize, attendance).
  - `services/face_service.py`: Logic xử lý face (detect, embedding, liveness).
  - `database/`: Models, schemas cho DB (SQLite).

- **face_engine/**: Core AI cho face processing.
  - `facenet/detect.py`: Phát hiện khuôn mặt dùng DeepFace RetinaFace.
  - `facenet/embedding.py`: Trích xuất embedding dùng Facenet512, và liveness detection.
  - `utils.py`: Utilities chung.

- **core/**: Config và constants.
  - `config.py`: Cấu hình hệ thống.

- **scripts/**: Benchmark và tools.
  - `benchmark_liveness_metrics.py`: Đánh giá anti-spoofing.
  - `benchmark_threshold.py`: Tìm ngưỡng nhận diện.

- **benchmarks/**: Kết quả benchmark (JSON reports).

- **dataset/**: Dữ liệu training/eval (liveness_eval cho anti-spoof).

- **frontend/**: UI React/Vite.

### 0.2 Phân tích code quan trọng

#### Face Detection (`face_engine/facenet/detect.py`)
- Sử dụng DeepFace với RetinaFace backend.
- Trả về list (face_image, bbox) với confidence > 0.7.
- Không dùng anti_spoofing ở đây (chỉ detect).

#### Embedding Extraction (`face_engine/facenet/embedding.py`)
- `get_embedding()`: Resize face to 160x160, dùng Facenet512, normalize embedding.
- `get_embedding_with_liveness()`: Chạy detect với anti_spoofing=True để lấy is_real, spoof_score.

#### Face Service (`backend/services/face_service.py`)
- Wrapper cho detect, embedding, liveness.
- Threshold mặc định 0.7 cho nhận diện.

#### Anti-Spoofing Logic
- Dùng DeepFace anti_spoofing với opencv detector.
- Trả về is_real (bool), spoof_score (float, 0-1).
- Reject nếu spoof_score >= threshold (mặc định 0.65, nhưng benchmark dùng 0.92).

### 0.3 Xử lý hình ảnh trích xuất đặc trưng phát hiện sinh viên đeo khẩu trang

- **Model sử dụng**: Facenet512 từ DeepFace, được train trên MS-Celeb-1M, có khả năng robust với occlusion như khẩu trang (nhưng không tối ưu).
- **Detection**: RetinaFace detect faces ngay cả khi có khẩu trang (landmarks bao gồm mắt, mũi).
- **Embedding**: Facenet512 trích xuất 512D vector từ face 160x160. Không có preprocessing đặc biệt cho mask, nhưng model generalize tốt.
- **Code chính**: `get_embedding()` trong `embedding.py` - resize, convert RGB, represent với Facenet512.

### 0.4 Anti-Spoofing: Phát hiện spoof qua đâu, ngưỡng

- **Phương pháp**: Dùng DeepFace anti_spoofing module, phân tích texture, motion, depth cues từ face image.
- **Detector**: opencv backend cho liveness.
- **Output**: is_real (True nếu real), spoof_score (0.0 = real, 1.0 = spoof).
- **Ngưỡng**: Mặc định 0.65 (script), nhưng benchmark dùng 0.92 để balance APCER/BPCER.
- **Logic reject**: Nếu is_real=False hoặc spoof_score >= threshold, reject.
- **Code**: `get_embedding_with_liveness()` gọi DeepFace.extract_faces với anti_spoofing=True.

## 1) Muc tieu migrate

- Thay doi mo hinh truy cap: khong con 1 admin hardcoded duy nhat.
- Moi account dang ky duoc quan ly nhu giang vien, qua quy trinh duyet cua admin.
- Giang vien chi tao va quan ly lop hoc minh giang day de diem danh chinh xac theo ownership.
- Giu va nang cap cac thanh phan AI hien co: liveness detection, incremental FAISS update, benchmark.
- Bo sung confidence visualization (top-3 candidates + cosine bar chart) de tang trust UX.
- Dong goi thanh dong gop hoc thuat ro rang (novelty + protocol danh gia).

## 2) Hien trang codebase (AS-IS)

### 2.1 Auth

- Login dang dung admin hardcoded qua bien cau hinh.
- Token hien tai khong chua role, endpoint xac thuc dang xu ly theo vai tro admin duy nhat.

### 2.2 Business model

- Chua co bang users/lecturers/classes/sessions.
- Attendance hien theo cap sinh vien + timestamp, chua ownership theo lop hoc/giang vien.

### 2.3 Face pipeline

- Da co liveness gate trong luong recognize.
- Da co FAISS index + benchmark script do latency, threshold.
- Chua co top-3 giai thich confidence cho giao dien giang vien.

## 3) Kien truc TO-BE

### 3.1 Role va quyen

- Role:
  - ADMIN: quan tri account, duyet giang vien, quan tri tong.
  - LECTURER: quan ly lop cua minh, mo/dong session, diem danh.
- Account status:
  - PENDING: vua dang ky, chua duyet.
  - ACTIVE: duoc phep dang nhap va thao tac theo role.
  - BLOCKED: bi khoa tam thoi.

### 3.2 Ownership nghiep vu

- Moi lop hoc co 1 owner la giang vien.
- Moi attendance session thuoc 1 lop hoc.
- Lecturer chi thay va thao tac du lieu trong ownership cua minh.
- Admin co quyen xem va can thiep toan cuc.

### 3.3 Nhan dien va diem danh

- Pipeline runtime:
  detect face -> liveness gate -> embedding -> FAISS top-k -> decision threshold -> ghi attendance session.
- Decision UX:
  neu confidence du cao thi auto-mark;
  neu confidence thap hoac gan nguong thi hien top-3 de lecturer quyet dinh thu cong.

## 4) Ke hoach migration du lieu (Schema)

Luu y: database hien tai la SQLite. Dung migration idempotent theo tung buoc.

### 4.1 Bang moi

1. users
- id INTEGER PRIMARY KEY AUTOINCREMENT
- username TEXT UNIQUE NOT NULL
- password_hash TEXT NOT NULL
- role TEXT NOT NULL CHECK(role IN ('ADMIN','LECTURER'))
- status TEXT NOT NULL CHECK(status IN ('PENDING','ACTIVE','BLOCKED'))
- created_at DATETIME DEFAULT CURRENT_TIMESTAMP
- updated_at DATETIME DEFAULT CURRENT_TIMESTAMP

2. lecturer_profiles
- id INTEGER PRIMARY KEY AUTOINCREMENT
- user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE
- full_name TEXT NOT NULL
- email TEXT
- phone TEXT
- department TEXT
- created_at DATETIME DEFAULT CURRENT_TIMESTAMP

3. registration_requests
- id INTEGER PRIMARY KEY AUTOINCREMENT
- username TEXT UNIQUE NOT NULL
- password_hash TEXT NOT NULL
- full_name TEXT NOT NULL
- email TEXT
- phone TEXT
- department TEXT
- status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED'))
- reviewed_by INTEGER NULL REFERENCES users(id)
- reviewed_at DATETIME NULL
- review_note TEXT
- created_at DATETIME DEFAULT CURRENT_TIMESTAMP

4. classes
- id INTEGER PRIMARY KEY AUTOINCREMENT
- code TEXT UNIQUE
- name TEXT NOT NULL
- lecturer_user_id INTEGER NOT NULL REFERENCES users(id)
- day_of_week INTEGER NULL
- start_time TEXT NULL
- end_time TEXT NULL
- room TEXT NULL
- term TEXT NULL
- active INTEGER DEFAULT 1
- created_at DATETIME DEFAULT CURRENT_TIMESTAMP

5. class_students
- class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE
- student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE
- created_at DATETIME DEFAULT CURRENT_TIMESTAMP
- PRIMARY KEY(class_id, student_id)

6. attendance_sessions
- id INTEGER PRIMARY KEY AUTOINCREMENT
- class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE
- opened_by INTEGER NOT NULL REFERENCES users(id)
- opened_at DATETIME NOT NULL
- closed_at DATETIME NULL
- status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED'))

7. attendance_records
- id INTEGER PRIMARY KEY AUTOINCREMENT
- session_id INTEGER NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE
- student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE
- status TEXT NOT NULL CHECK(status IN ('PRESENT','LATE','ABSENT'))
- method TEXT NOT NULL CHECK(method IN ('FACE','MANUAL'))
- score REAL NOT NULL DEFAULT 0.0
- modified_by INTEGER NULL REFERENCES users(id)
- modified_at DATETIME DEFAULT CURRENT_TIMESTAMP
- UNIQUE(session_id, student_id)

8. recognition_events (de benchmark va giai thich)
- id INTEGER PRIMARY KEY AUTOINCREMENT
- session_id INTEGER NULL REFERENCES attendance_sessions(id)
- lecturer_user_id INTEGER NULL REFERENCES users(id)
- student_id_pred INTEGER NULL REFERENCES students(id)
- is_liveness_pass INTEGER NOT NULL
- spoof_score REAL NOT NULL
- top1_student_id INTEGER NULL
- top1_score REAL NULL
- top2_student_id INTEGER NULL
- top2_score REAL NULL
- top3_student_id INTEGER NULL
- top3_score REAL NULL
- decision TEXT NOT NULL CHECK(decision IN ('AUTO_MARK','MANUAL_REVIEW','REJECT'))
- created_at DATETIME DEFAULT CURRENT_TIMESTAMP

### 4.2 Migration strategy

- M0: backup attendance.db.
- M1: tao bang moi va index.
- M2: tao account admin dau tien tu env.
- M3: bo sung cot metadata cho token payload (role, status).
- M4: giu bang attendance cu cho backward compatibility, them adapter doc song song.
- M5: cut-over sang attendance_records theo session.

## 5) API Contract blueprint

## 5.1 Auth + Register lecturer

1. POST /api/auth/register-lecturer
Request:
- username, password, full_name, email, phone, department
Response:
- 201 + request_id, status=PENDING

2. POST /api/auth/login
Request:
- username, password
Response:
- access_token, token_type, user(role,status,profile)

3. GET /api/auth/verify
Response:
- user(role,status)

4. POST /api/logout
Response:
- revoke token thanh cong

## 5.2 Admin APIs

1. GET /api/admin/registration-requests?status=PENDING
2. POST /api/admin/registration-requests/{id}/approve
3. POST /api/admin/registration-requests/{id}/reject
4. GET /api/admin/lecturers
5. PATCH /api/admin/lecturers/{user_id}/status  (ACTIVE/BLOCKED)
6. GET /api/admin/dashboard/summary

## 5.3 Lecturer class ownership APIs

1. POST /api/lecturer/classes
2. GET /api/lecturer/classes
3. GET /api/lecturer/classes/{id}
4. PATCH /api/lecturer/classes/{id}
5. DELETE /api/lecturer/classes/{id}
6. POST /api/lecturer/classes/{id}/students:bind
7. DELETE /api/lecturer/classes/{id}/students/{student_id}

## 5.4 Session attendance APIs

1. POST /api/lecturer/classes/{class_id}/sessions/open
- tao session moi, khoi tao ABSENT cho tat ca student trong class

2. POST /api/lecturer/sessions/{session_id}/recognize
- version role-aware cua /recognize
- chi chap nhan neu session thuoc lecturer dang login

3. PATCH /api/lecturer/sessions/{session_id}/records/{student_id}
- manual override PRESENT/LATE/ABSENT

4. POST /api/lecturer/sessions/{session_id}/close

5. GET /api/lecturer/sessions/{session_id}/records
6. GET /api/lecturer/classes/{class_id}/history

## 5.5 Confidence visualization API

Duy tri endpoint /api/recognize cho compatibility, tao endpoint moi uu tien:

POST /api/lecturer/sessions/{session_id}/recognize
Response cho moi khuon mat:
- face_id
- bbox
- liveness: {is_real, spoof_score}
- decision: AUTO_MARK | MANUAL_REVIEW | REJECT
- matched: {student_id, name, score} hoac null
- top_candidates: [
  {rank:1, student_id, name, cosine_score},
  {rank:2, student_id, name, cosine_score},
  {rank:3, student_id, name, cosine_score}
]
- threshold_used

Rule goi y:
- cosine >= auto_mark_threshold va liveness pass -> AUTO_MARK
- nguoc lai neu trong vung uncertainty -> MANUAL_REVIEW
- neu spoof fail -> REJECT

## 6) Thay doi backend theo module

### 6.1 database/db.py

- Them init schema cho users, lecturers, classes, sessions, records.
- Them helper query ownership:
  - is_admin(user_id)
  - is_lecturer(user_id)
  - owns_class(user_id, class_id)
  - owns_session(user_id, session_id)
- Them CRUD cho registration_requests va lecturers.

### 6.2 api/routes.py

- Tach Auth router rieng:
  - login/register/verify/logout
- Them dependency get_current_user, require_role, require_active_user.
- Chuyen get_current_admin hien tai thanh require_role('ADMIN').
- Bo sung router admin va lecturer theo contract.
- /recognize: bo sung top-3 va decision object; log recognition_events.

### 6.3 services/face_service.py + faiss_search.py

- face_service.recognize hien tra top1; can them:
  - recognize_topk(embedding, top_k=3, threshold)
- faiss_search them ham tra top-k:
  - search_topk(query_embedding, top_k)
  - output danh sach (student_id, similarity) da sap xep
- Giu backward-compatible recognize de tranh vo giao dien cu.

### 6.4 attendance_service.py

- them mark_attendance_for_session(session_id, student_id, method, score, by_user)
- them init_session_absent_records(session_id)
- them close_session(session_id)

## 7) Thay doi frontend

### 7.1 AuthContext

- state can giu:
  - token
  - user: {id, username, role, status, profile}
- sau login, route theo role:
  - ADMIN -> admin app shell
  - LECTURER -> lecturer app shell

### 7.2 LoginPanel

- bo sung link dang ky account giang vien.
- hien trang thai account:
  - PENDING: cho duyet
  - BLOCKED: lien he admin

### 7.3 Admin dashboard

- tab quan ly dang ky: pending list + approve/reject.
- tab quan ly giang vien: active/blocked + thong ke.

### 7.4 Lecturer dashboard

- tab Lop cua toi: CRUD class.
- tab Session diem danh: open/recognize/manual override/close.
- tab Lich su: xem theo lop va xuat bao cao.

### 7.5 Confidence visualization trong AttendancePanel

- sau moi lan recognize, nhan top_candidates.
- hien panel ben phai:
  - top-3 theo tung face
  - thanh bar score (0-1)
  - mau:
    - xanh: auto mark
    - vang: can xem xet
    - do: reject/spoof
- them tooltip ngan giai thich:
  - score gan nguong => de nham lan
  - nen xac nhan thu cong

## 8) Incremental FAISS update blueprint

## 8.1 Muc tieu

- Khong rebuild full index cho moi thay doi nho.
- Ho tro add/remove/update embedding theo su kien.

## 8.2 Lua chon ky thuat

Option A (de lam nhanh):
- Van dung IndexFlatL2, khi co thay doi nho thi rebuild nhanh tu cache memory.
- Bo sung debounce window 2-5 giay de gom batch update.

Option B (nang cao hoc thuat):
- Dung IndexIDMap2 de map vector voi embedding_id.
- Ho tro add_with_ids va remove_ids.
- Dinh ky nightly rebuild de giam fragmentation.

Khuyen nghi:
- Phase 1 dung Option A de on dinh.
- Phase 2 nang cap Option B de co novelty nghien cuu ro hon.

## 8.3 Trigger update

- Sau register nhieu anh thanh cong.
- Sau delete student.
- Sau edit embedding quality (neu co).

## 9) Benchmark va quan sat he thong

### 9.1 Benchmark can bao cao

1. Latency
- detect
- liveness
- embedding
- faiss search
- end-to-end recognize

2. Accuracy
- precision/recall/f1 theo threshold
- FAR/FRR
- confusion matrix theo dieu kien anh sang

3. Security
- spoof detection rate
- false reject khi nguoi that

4. Ops
- ty le recognize vao MANUAL_REVIEW
- ty le auto-mark dung

### 9.2 Logging

- Ghi recognition_events cho moi phien.
- Co trace_id/session_id de debug.

## 10) Lo trinh trien khai (4 tuan)

### Tuan 1
- Lam schema migration M1-M2.
- Implement auth role-based, register lecturer, admin approve/reject.
- Refactor middleware role checks.

### Tuan 2
- Implement class ownership CRUD + class_students.
- Implement open/close session + attendance_records.
- Frontend tach 2 app shell (admin/lecturer).

### Tuan 3
- Them recognize role-aware theo session.
- Them top-3 candidates + confidence bars UI.
- Them recognition_events logging.

### Tuan 4
- Hoan thien incremental FAISS strategy da chon.
- Chay benchmark full, ra report va bieu do.
- Hardening + UAT + chot tai lieu hoc thuat.

## 11) Acceptance criteria

### 11.1 Auth va role
- Account khong role ADMIN khong truy cap duoc admin APIs.
- Account PENDING/BLOCKED khong vao duoc chuc nang nghiep vu.

### 11.2 Ownership
- Lecturer A khong the doc/ghi class/session cua Lecturer B.
- Admin xem duoc toan bo.

### 11.3 Session attendance
- Moi student chi co toi da 1 record/session.
- Co manual override va audit modified_by, modified_at.

### 11.4 Recognition UX
- Moi face tra top-3 candidates + score.
- Vung uncertainty hien MANUAL_REVIEW thay vi auto-mark.
- Liveness fail thi REJECT, khong diem danh.

### 11.5 Benchmark
- Co report json va tom tat metric.
- So sanh truoc/sau migrate cho latency va quality.

## 12) De xuat dong gop hoc thuat

## 12.1 Phat bieu bai toan

Bai toan khong chi la face recognition don le, ma la bai toan diem danh theo ngu canh giao duc co rang buoc nghiep vu, bao mat, va tinh giai thich trong quyet dinh.

## 12.2 Dong gop moi de nhan manh

1. Business-aware face attendance
- Ket hop role-based ownership voi session attendance de tranh sai quyen, sai lop.

2. Explainable recognition for human-in-the-loop
- Top-3 candidates + cosine bars giup lecturer dua ra quyet dinh thu cong o vung uncertainty.

3. Liveness-gated attendance policy
- Liveness duoc dua vao policy quyet dinh thay vi chi la plugin minh hoa.

4. Incremental vector index maintenance
- Co co che update index theo su kien, giam downtime va chi phi rebuild.

5. End-to-end benchmark framework
- Danh gia dong thoi accuracy, latency, anti-spoof, va quality quy trinh nghiep vu.

## 12.3 Khung thuc nghiem de viet bao cao

- Baseline A: khong liveness, chi top1.
- Baseline B: co liveness, top1.
- Proposed C: co liveness + top3 + manual-review policy + ownership session.

So sanh theo:
- do chinh xac diem danh thuc te
- ty le spoof pass
- ty le can manual review
- latency p50/p95
- muc do hai long nguoi dung (lecturer survey ngan)

## 13) Risk va giam thieu

1. Risk: migration schema lam vo API cu.
- Giam thieu: giu compatibility layer 1-2 sprint.

2. Risk: top-3 lam giao dien phuc tap.
- Giam thieu: chi hien khi score top1 nam trong uncertainty band.

3. Risk: incremental update gay lech index.
- Giam thieu: co periodic full rebuild + checksum cache.

4. Risk: lecturer ownership sai do lieu map.
- Giam thieu: test integration bat buoc cho quy tac phan quyen.

## 14) Danh sach implementation tickets (de giao viec)

- BE-001: Tao schema users/lecturers/registration_requests.
- BE-002: Implement auth register/login/verify role-based.
- BE-003: Admin APIs approve/reject/block lecturer.
- BE-004: Schema classes/class_students/sessions/records.
- BE-005: Lecturer class ownership CRUD APIs.
- BE-006: Session attendance APIs + unique(session_id, student_id).
- BE-007: Recognize top-3 + decision object + recognition_events log.
- BE-008: FAISS top-k search + incremental update strategy.
- FE-001: AuthContext luu user role/status.
- FE-002: Login + Register lecturer flows.
- FE-003: Admin dashboard quan ly account.
- FE-004: Lecturer class/session screens.
- FE-005: Confidence visualization (bar chart + decision badge).
- QA-001: RBAC + ownership integration tests.
- QA-002: Benchmark scripts pipeline va report.
- DOC-001: Cap nhat docs kien truc + huong dan van hanh.

## 15) Definition of Done cho migration

- Role-based auth va lecturer ownership chay production mode.
- Admin dashboard quan ly account giang vien hoat dong day du.
- Session attendance theo lop cua giang vien da thay the flow cu.
- Confidence top-3 visualization da xuat hien trong luong diem danh.
- Liveness + FAISS + benchmark co so lieu truoc/sau migrate.
- Tai lieu hoc thuat va bao cao metric san sang cho bao ve/demo.
