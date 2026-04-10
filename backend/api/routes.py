from fastapi import APIRouter, UploadFile, File, HTTPException, status, Form, Query, Header
from fastapi.responses import StreamingResponse
import numpy as np
import cv2
import logging
import csv
import sqlite3
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
    get_student_by_mssv,
    delete_student_and_embedding,
    get_attendance_range,
    get_attendance_by_student,
    get_all_embeddings,
    create_student,
    save_embedding,
    DB_PATH
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
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file size

# ====================== SERVICES ======================
face_service = FaceService(threshold=0.01)
attendance_service = AttendanceService()
register_service = RegisterService()

# ====================== CACHE ======================
# Lưu embeddings cache (sẽ được cập nhật từ main.py)
embeddings_cache: List[tuple] = []

def update_embeddings_cache():
    """Reload embeddings cache từ database"""
    global embeddings_cache
    embeddings_cache.clear()
    embeddings_cache.extend(get_all_embeddings())
    logger.info(f"📦 Đã update cache: {len(embeddings_cache)} embeddings")

# ====================== HELPER FUNCTIONS ======================
def validate_image_file(file: UploadFile, max_size: int = MAX_FILE_SIZE) -> bool:
    """Validate image file type and size"""
    # Kiểm tra content_type nếu được cung cấp
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File phải là ảnh")
    
    # Nếu content_type không được cung cấp, kiểm tra extension
    if not file.content_type:
        filename = file.filename or ""
        file_ext = filename.lower().split('.')[-1] if '.' in filename else ""
        if file_ext not in {'jpg', 'jpeg', 'png', 'bmp', 'webp', 'gif'}:
            raise HTTPException(status_code=400, detail="File phải là ảnh (jpg, png, bmp, webp, gif)")
    
    if file.size and file.size > max_size:
        raise HTTPException(
            status_code=413, 
            detail=f"File quá lớn. Tối đa {max_size / 1024 / 1024:.0f}MB"
        )
    return True


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
        update_embeddings_cache()

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
    try:
        get_current_admin(authorization)

        if not name or not name.strip():
            raise HTTPException(status_code=400, detail="Tên sinh viên không được để trống")

        # Validate file
        validate_image_file(file)

        logger.info(f"Dataset register cho sinh viên: {name}, MSSV: {mssv}")

        contents = await file.read()
        
        # Validate MSSV nếu có
        if mssv and mssv.strip():
            mssv = mssv.strip()
            existing_mssv = get_student_by_mssv(mssv)
            if existing_mssv:
                raise HTTPException(
                    status_code=400, 
                    detail=f"MSSV '{mssv}' đã tồn tại với sinh viên: {existing_mssv['name']}"
                )

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
        register_file = BytesIO(contents)
        success, message, student_id = register_service.register_student(name, mssv=mssv, file=register_file)

        if not success:
            raise HTTPException(status_code=400, detail=message)

        save_dataset_image(name, file.filename or f"{name}.jpg", contents)

        # Reload cache
        update_embeddings_cache()

        return RegisterResponse(
            status="success",
            message=message,
            data={"student_id": student_id, "name": name, "mssv": mssv}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Lỗi không xác định khi đăng ký '{name}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


@router.post("/dataset/register-multiple", response_model=RegisterResponse)
async def register_dataset_multiple(
    name: str = Form(...),
    mssv: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    authorization: Optional[str] = Header(None)
):
    """Đăng ký + lưu múltiplos ảnh từ các góc khác nhau"""
    try:
        get_current_admin(authorization)

        if not name or not name.strip():
            raise HTTPException(status_code=400, detail="Tên sinh viên không được để trống")

        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="Phải gửi ít nhất 1 ảnh")

        logger.info(f"Dataset register múltiplo cho sinh viên: {name}, MSSV: {mssv}, Số ảnh: {len(files)}")

        # Validate all files
        for file in files:
            validate_image_file(file)

        # Validate MSSV nếu có
        if mssv and mssv.strip():
            mssv = mssv.strip()
            existing_mssv = get_student_by_mssv(mssv)
            if existing_mssv:
                raise HTTPException(
                    status_code=400, 
                    detail=f"MSSV '{mssv}' đã tồn tại với sinh viên: {existing_mssv['name']}"
                )

        # Kiểm tra sinh viên đã tồn tại chưa
        existing = get_student_by_name(name)
        if existing:
            # Nếu đã tồn tại, chỉ lưu ảnh
            for file in files:
                contents = await file.read()
                save_dataset_image(name, file.filename or f"{name}.jpg", contents)
            return RegisterResponse(
                status="success",
                message=f"Sinh viên đã tồn tại. {len(files)} ảnh được lưu vào dataset",
                data={"student_id": existing["id"], "name": name, "mssv": mssv}
            )

        # Đăng ký mới - xử lý tất cả ảnh
        student_id = create_student(name, mssv)
        embeddings_saved = 0

        for file in files:
            contents = await file.read()
            
            # Trích xuất embedding
            np_arr = np.frombuffer(contents, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame is None:
                logger.warning(f"Không thể đọc file ảnh: {file.filename}")
                continue

            faces = face_service.detect(frame)
            
            if not faces:
                logger.warning(f"Không phát hiện khuôn mặt trong {file.filename}")
                continue

            # Lấy khuôn mặt đầu tiên
            face_image = faces[0]
            embedding = face_service.extract_embedding(face_image)
            save_embedding(student_id, embedding)
            embeddings_saved += 1

            # Lưu ảnh gốc
            save_dataset_image(name, file.filename or f"{name}_{embeddings_saved}.jpg", contents)

        if embeddings_saved == 0:
            raise HTTPException(status_code=400, detail="Không thể trích xuất embedding từ các ảnh")

        # Reload cache
        update_embeddings_cache()

        logger.info(f"✅ Đăng ký múltiplo thành công - Student ID: {student_id} | Name: {name} | Embeddings: {embeddings_saved}")

        return RegisterResponse(
            status="success",
            message=f"Đăng ký thành công với {embeddings_saved} ảnh",
            data={"student_id": student_id, "name": name, "mssv": mssv}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Lỗi không xác định khi đăng ký múltiplo '{name}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


# ====================== RECOGNIZE ======================
@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(file: UploadFile = File(...)):
    """Nhận diện khuôn mặt và điểm danh (không cần auth)"""
    logger.info(f"Recognize request - File: {file.filename}")

    # Validate file
    validate_image_file(file)

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


@router.put("/students/{student_id}", response_model=StudentDetailResponse)
async def update_student(
    student_id: int,
    name: str = Form(...),
    authorization: Optional[str] = Header(None)
):
    """Cập nhật tên sinh viên"""
    get_current_admin(authorization)
    
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Tên sinh viên không được để trống")
    
    # Check student exists
    student = get_student_by_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên")
    
    # Update logic
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE students SET name = ? WHERE id = ?",
            (name.strip(), student_id)
        )
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Cập nhật sinh viên ID {student_id} thành công: {name}")
        
        updated_student = get_student_by_id(student_id)
        return StudentDetailResponse(
            status="success",
            message="Cập nhật tên sinh viên thành công",
            data=updated_student
        )
    except Exception as e:
        logger.error(f"Lỗi cập nhật sinh viên: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi cập nhật sinh viên")


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
        update_embeddings_cache()
        
        return {"status": "success", "message": f"Đã xóa sinh viên ID {student_id} và dữ liệu liên quan"}
    
    raise HTTPException(status_code=400, detail="Xóa thất bại")