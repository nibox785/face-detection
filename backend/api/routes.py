from fastapi import APIRouter, UploadFile, File, HTTPException, status, Form, Query
import numpy as np
import cv2
import logging
from typing import  Optional, List, Dict, Any

from backend.services.face_service import FaceService
from backend.services.attendance_service import AttendanceService

from fastapi import Form
from backend.services.register_service import RegisterService

from backend.database.db import (
    get_all_students,
    get_student_by_id,
    delete_student_and_embedding,
    get_attendance_range,
    get_attendance_by_student,
    get_all_embeddings
)
from backend.database.schemas import (
    ApiResponse,
    StudentListResponse,
    StudentDetailResponse,
    AttendanceResponse,
    RecognizeResponse,
    RegisterResponse,
    RecognizeResult
)

router = APIRouter()

# Khởi tạo service
face_service = FaceService(threshold=0.7)
attendance_service = AttendanceService()
register_service = RegisterService()

logger = logging.getLogger("face-attendance.routes")

# Cache embeddings (được cập nhật từ main.py)
embeddings_cache: List[tuple] = []


@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    API nhận diện khuôn mặt và điểm danh tự động.
    Hỗ trợ nhận diện nhiều khuôn mặt trong một ảnh.
    """
    logger.info(f"Nhận request recognize - Filename: {file.filename}")

    # Validate content type
    if not file.content_type or not file.content_type.startswith("image/"):
        logger.warning(f"Invalid content type: {file.content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File upload phải là ảnh (image/jpeg, image/png, ...)"
        )

    try:
        # Đọc file
        contents = await file.read()
        logger.debug(f"Đã đọc file, kích thước: {len(contents)} bytes")

        # Convert sang image
        np_arr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không thể đọc được file ảnh"
            )

        # Detect faces
        faces = face_service.detect(frame)
        
        if not faces:
            logger.info("Không phát hiện khuôn mặt nào")
            return RecognizeResponse(
                status="success",
                message= "Không phát hiện được khuôn mặt nào trong ảnh.",
                data=[]
            )

        logger.info(f"Phápip install deepface --no-deps hiện {len(faces)} khuôn mặt")

        # Recognize từng khuôn mặt
        results: List[RecognizeResult] = []       

        for i, face in enumerate(faces):
            embedding = face_service.extract_embedding(face)
            student_id, score = face_service.recognize(embedding, embeddings_cache)

            # Điểm danh nếu nhận diện được
            if student_id:
                attendance_service.mark_attendance(student_id)
                logger.info(f"Đã điểm danh cho student_id: {student_id}")

            results.append(
                RecognizeResult(
                student_id= student_id,
                score=round(float(score), 4)
                )
            )
        

        return RecognizeResponse(
            status="success",
            message=f"Đã xử lý {len(faces)} khuôn mặt.",
            data=results
        )

    except Exception as e:
        logger.error(f"Lỗi không xác định trong /recognize: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi server khi xử lý nhận diện"
        )


@router.post("/register", response_model=RegisterResponse)
async def register(
    name: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Đăng ký sinh viên mới với ảnh khuôn mặt
    """
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Tên sinh viên không được để trống")
    
    logger.info(f"Nhận request register cho sinh viên: {name}")

    success, message, student_id = register_service.register_student(name, file)

    if success:
        # Reload cache sau khi register
        from backend.database.db import get_all_embeddings
        global embeddings_cache
        embeddings_cache.clear()
        embeddings_cache.extend(get_all_embeddings())

        return RegisterResponse(
            status= "success",
            message= message,
            data={"student_id": student_id, "name": name}
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
# ==================== GET ENDPOINTS ====================

@router.get("/students", response_model=StudentListResponse)
async def get_students():
    """Lấy danh sách tất cả sinh viên"""
    students = get_all_students()
    return StudentListResponse(
        status="success",
        message="Lấy danh sách sinh viên thành công",
        data=students
    )


@router.get("/students/{student_id}", response_model=StudentDetailResponse)
async def get_student(student_id: int):
    """Lấy thông tin chi tiết một sinh viên"""
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
    end_date: Optional[str] = Query(None)
):
    """Lấy danh sách điểm danh"""
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


@router.delete("/students/{student_id}")
async def delete_student(student_id: int):
    """Xóa sinh viên và dữ liệu liên quan"""
    success = delete_student_and_embedding(student_id)
    if success:
        global embeddings_cache
        embeddings_cache.clear()
        embeddings_cache.extend(get_all_embeddings())
        
        return {"status": "success", "message": f"Đã xóa sinh viên ID {student_id}"}
    
    raise HTTPException(status_code=400, detail="Xóa thất bại")