from fastapi import APIRouter, UploadFile, File, HTTPException, status, Form, Query, Header
from fastapi.responses import StreamingResponse
import numpy as np
import cv2
import logging
import csv
from io import StringIO, BytesIO
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from backend.services.face_service import FaceService
from backend.services.attendance_service import AttendanceService
from backend.services.register_service import RegisterService

from backend.database.db import (
    get_all_students,
    get_student_by_id,
    get_student_by_name,
    delete_student_and_embedding,
    get_attendance_range,
    get_attendance_by_student,
    get_all_embeddings
)
from backend.database.schemas import (
    RecognizeResponse,
    RecognizeResult,
    RegisterResponse,
    StudentListResponse,
    StudentDetailResponse,
    AttendanceResponse,
    LoginResponse,
    LoginRequest
)

from core.config import ADMIN_USERNAME, ADMIN_PASSWORD, SECRET_KEY, ACCESS_TOKEN_EXPIRE_SECONDS

# ====================== CONFIG ======================
router = APIRouter()
logger = logging.getLogger("face-attendance.routes")

DATASET_ROOT = Path("dataset")
DATASET_ROOT.mkdir(parents=True, exist_ok=True)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# ====================== SERVICES ======================
face_service = FaceService(threshold=0.7)
attendance_service = AttendanceService()
register_service = RegisterService()

# ====================== CACHE ======================
embeddings_cache: List[tuple] = []


# ====================== HELPER FUNCTIONS ======================
def sanitize_student_name(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name.strip())
    return safe.replace(" ", "_") or "student"


def save_dataset_image(student_name: str, filename: str, contents: bytes) -> str:
    safe_name = sanitize_student_name(student_name)
    student_dir = DATASET_ROOT / safe_name
    student_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix.lower() if filename else ".jpg"
    if ext not in IMAGE_EXTENSIONS:
        ext = ".jpg"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = student_dir / f"{timestamp}{ext}"
    
    with open(destination, "wb") as f:
        f.write(contents)
    
    return str(destination)


def create_access_token(data: dict, expires_seconds: int = ACCESS_TOKEN_EXPIRE_SECONDS) -> str:
    """Tạo token đơn giản (có thể thay bằng PyJWT sau)"""
    import json, base64, hmac, time
    from hashlib import sha256

    payload = data.copy()
    payload["exp"] = int(time.time()) + expires_seconds
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
    signature = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_access_token(token: str) -> dict:
    """Xác thực token"""
    try:
        import json, base64, hmac, time
        from hashlib import sha256

        payload_b64, signature = token.rsplit('.', 1)
        expected = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), sha256).hexdigest()

        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Token không hợp lệ")

        padded = payload_b64 + '=' * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())

        if payload.get('exp') is None or int(payload['exp']) < int(time.time()):
            raise HTTPException(status_code=401, detail="Token đã hết hạn")

        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")


def get_current_admin(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Yêu cầu đăng nhập (Bearer token)")
    
    token = authorization.split(' ', 1)[1]
    return verify_access_token(token)


# ====================== AUTH ======================
@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    if request.username != ADMIN_USERNAME or request.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng")

    access_token = create_access_token({"sub": request.username})
    return LoginResponse(
        status="success",
        message="Đăng nhập thành công",
        data={"access_token": access_token, "token_type": "bearer"}
    )


# ====================== REGISTER ======================
@router.post("/register", response_model=RegisterResponse)
async def register(
    name: str = Form(...),
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """Đăng ký sinh viên mới (yêu cầu quyền admin)"""
    get_current_admin(authorization)

    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Tên sinh viên không được để trống")

    logger.info(f"Register sinh viên: {name}")

    success, message, student_id = register_service.register_student(name, file)

    if success:
        # Reload cache
        global embeddings_cache
        embeddings_cache.clear()
        embeddings_cache.extend(get_all_embeddings())

        return RegisterResponse(
            status="success",
            message=message,
            data={"student_id": student_id, "name": name}
        )
    else:
        raise HTTPException(status_code=400, detail=message)


@router.post("/dataset/register", response_model=RegisterResponse)
async def register_dataset(
    name: str = Form(...),
    mssv: Optional[str] = Form(None),
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """Đăng ký + lưu ảnh gốc vào dataset"""
    get_current_admin(authorization)

    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Tên sinh viên không được để trống")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File phải là ảnh")

    logger.info(f"Dataset register cho sinh viên: {name}, MSSV: {mssv}")

    contents = await file.read()

    # Kiểm tra sinh viên đã tồn tại chưa
    existing = get_student_by_name(name)
    if existing:
        saved_path = save_dataset_image(name, file.filename or f"{name}.jpg", contents)
        return RegisterResponse(
            status="success",
            message=f"Sinh viên đã tồn tại. Ảnh được lưu vào dataset: {saved_path}",
            data={"student_id": existing["id"], "name": name, "mssv": mssv}
        )

    # Đăng ký mới
    register_file = BytesIO(contents) if 'BytesIO' in globals() else contents
    success, message, student_id = register_service.register_student(name,mssv = mssv, file=register_file)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    save_dataset_image(name, file.filename or f"{name}.jpg", contents)

    # Reload cache
    global embeddings_cache
    embeddings_cache.clear()
    embeddings_cache.extend(get_all_embeddings())

    return RegisterResponse(
        status="success",
        message=message,
        data={"student_id": student_id, "name": name, "mssv": mssv}
    )


# ====================== RECOGNIZE ======================
@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(file: UploadFile = File(...)):
    """Nhận diện khuôn mặt và điểm danh (không cần auth)"""
    logger.info(f"Recognize request - File: {file.filename}")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File upload phải là ảnh")

    try:
        contents = await file.read()
        np_arr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Không thể đọc được file ảnh")

        faces = face_service.detect(frame)

        if not faces:
            return RecognizeResponse(
                status="success",
                message="Không phát hiện được khuôn mặt nào trong ảnh.",
                data=[]
            )

        logger.info(f"Phát hiện {len(faces)} khuôn mặt")

        results: List[RecognizeResult] = []

        for face in faces:
            embedding = face_service.extract_embedding(face)
            student_id, score = face_service.recognize(embedding, embeddings_cache)

            if student_id:
                attendance_service.mark_attendance(student_id)
                logger.info(f"Điểm danh thành công - Student ID: {student_id} | Score: {score:.4f}")

            results.append(
                RecognizeResult(
                    student_id=student_id,
                    score=round(float(score), 4)
                )
            )

        return RecognizeResponse(
            status="success",
            message=f"Đã xử lý {len(faces)} khuôn mặt.",
            data=results
        )

    except Exception as e:
        logger.error(f"Lỗi recognize: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi server khi xử lý nhận diện")


# ====================== MANAGEMENT API ======================
@router.get("/students", response_model=StudentListResponse)
async def get_students(authorization: Optional[str] = Header(None)):
    get_current_admin(authorization)
    students = get_all_students()
    return StudentListResponse(
        status="success",
        message="Lấy danh sách sinh viên thành công",
        data=students
    )


@router.get("/students/{student_id}", response_model=StudentDetailResponse)
async def get_student(student_id: int, authorization: Optional[str] = Header(None)):
    get_current_admin(authorization)
    student = get_student_by_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên")
    
    return StudentDetailResponse(
        status="success",
        message="Lấy thông tin sinh viên thành công",
        data=student
    )


@router.get("/attendance", response_model=AttendanceResponse)
async def get_attendance(
    student_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None)
):
    get_current_admin(authorization)

    if student_id:
        records = get_attendance_by_student(student_id)
        msg = f"Lấy điểm danh của sinh viên {student_id}"
    else:
        records = get_attendance_range(start_date, end_date)
        msg = "Lấy danh sách điểm danh"

    return AttendanceResponse(
        status="success",
        message=msg,
        data=records
    )


@router.get("/attendance/export")
async def export_attendance(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None)
):
    get_current_admin(authorization)
    records = get_attendance_range(start_date, end_date)

    # Tạo CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Student_ID", "Name", "Timestamp"])
    for r in records:
        writer.writerow([r.get("id"), r.get("student_id"), r.get("name"), r.get("timestamp")])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance_report.csv"}
    )


@router.delete("/students/{student_id}")
async def delete_student(student_id: int, authorization: Optional[str] = Header(None)):
    get_current_admin(authorization)
    
    success = delete_student_and_embedding(student_id)
    if success:
        global embeddings_cache
        embeddings_cache.clear()
        embeddings_cache.extend(get_all_embeddings())
        
        return {"status": "success", "message": f"Đã xóa sinh viên ID {student_id} và dữ liệu liên quan"}
    
    raise HTTPException(status_code=400, detail="Xóa thất bại")