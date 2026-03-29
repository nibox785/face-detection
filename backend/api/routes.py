from fastapi import APIRouter, UploadFile, File, HTTPException, status
import numpy as np
import cv2
import logging
from typing import List, Dict, Any

from backend.services.face_service import FaceService
from backend.services.attendance_service import AttendanceService

from fastapi import Form
from backend.services.register_service import RegisterService

router = APIRouter()

# Khởi tạo service
face_service = FaceService(threshold=0.7)
attendance_service = AttendanceService()

logger = logging.getLogger("face-attendance.routes")

# Cache embeddings (được cập nhật từ main.py)
embeddings_cache: List[tuple] = []


@router.post("/recognize")
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
            return {
                "results": [],
                "message": "Không phát hiện được khuôn mặt nào trong ảnh."
            }

        logger.info(f"Phát hiện {len(faces)} khuôn mặt")

        # Recognize từng khuôn mặt
        results = []
        
        for i, face in enumerate(faces):
            embedding = face_service.extract_embedding(face)
            student_id, score = face_service.recognize(embedding, embeddings_cache)

            # Điểm danh nếu nhận diện được
            if student_id:
                attendance_service.mark_attendance(student_id)
                logger.info(f"Đã điểm danh cho student_id: {student_id}")

            results.append({
                "student_id": student_id,
                "score": round(float(score), 4)
            })

        return {
            "results": results,
            "message": f"Đã xử lý {len(faces)} khuôn mặt."
        }

    except Exception as e:
        logger.error(f"Lỗi không xác định trong /recognize: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi server khi xử lý nhận diện"
        )

# Khởi tạo RegisterService
register_service = RegisterService()


@router.post("/register")
async def register(
    name: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Đăng ký sinh viên mới với ảnh khuôn mặt
    """
    logger.info(f"Nhận request register cho sinh viên: {name}")

    success, message, student_id = register_service.register_student(name, file)

    if success:
        return {
            "status": "success",
            "message": message,
            "student_id": student_id
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )