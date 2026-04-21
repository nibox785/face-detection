import logging
import cv2
import numpy as np
from typing import Optional, Tuple
from io import BytesIO

from backend.database.db import (
    save_embedding, 
    create_student, 
    get_student_by_name,
    get_student_by_mssv,
)
from backend.services.face_service import FaceService

logger = logging.getLogger("face-attendance.register_service")


class RegisterService:
    def __init__(self):
        self.face_service = FaceService()
        logger.info("RegisterService được khởi tạo")

    def register_student(self, name: str, mssv: str = None, file=None) -> Tuple[bool, str, Optional[int]]:
        """
        Đăng ký sinh viên mới:
        - Kiểm tra sinh viên đã tồn tại chưa
        - Nhận tên + ảnh
        - Detect face → Extract embedding
        - Lưu vào database qua hàm create_student()
        """
        try:
            # Đọc nội dung file ảnh (hỗ trợ cả UploadFile và bytes/BytesIO)
            if hasattr(file, 'file'):           # FastAPI UploadFile
                contents = file.file.read()
            elif hasattr(file, 'read'):         # BytesIO hoặc file-like object
                contents = file.read()
            else:                               # bytes thô
                contents = file

            if not contents:
                return False, "File ảnh rỗng hoặc không đọc được", None

            # Convert sang numpy array
            np_arr = np.frombuffer(contents, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                return False, "Không thể đọc được file ảnh. File có thể bị hỏng.", None

            # Phát hiện khuôn mặt
            faces = self.face_service.detect(frame)
            if not faces:
                return False, "Không phát hiện được khuôn mặt nào trong ảnh", None

            if len(faces) > 1:
                logger.warning(f"Phát hiện {len(faces)} khuôn mặt khi đăng ký. Chỉ sử dụng khuôn mặt đầu tiên.")

            # Lấy khuôn mặt rõ nhất (thường là khuôn mặt đầu tiên)
            first_face = faces[0]
            face_image = first_face[0] if isinstance(first_face, tuple) else first_face

            # Trích xuất embedding
            embedding = self.face_service.extract_embedding(face_image)

            # Ưu tiên MSSV để tránh gộp nhầm sinh viên trùng tên.
            existing = get_student_by_mssv(mssv) if mssv and mssv.strip() else get_student_by_name(name)
            if existing:
                logger.info(f"Sinh viên '{name}' đã tồn tại (ID: {existing['id']})")
                return True, f"Sinh viên '{name}' đã tồn tại", existing["id"]

            # Tạo sinh viên mới qua hàm db
            student_id = create_student(name, mssv)

            # Lưu embedding
            save_embedding(student_id, embedding)

            logger.info(f"✅ Đăng ký thành công - Student ID: {student_id} | Name: {name}| MSSV: {mssv}")
            return True, "Đăng ký sinh viên thành công", student_id

        except Exception as e:
            logger.error(f"Lỗi khi đăng ký sinh viên '{name}': {str(e)}", exc_info=True)
            return False, f"Lỗi server: {str(e)}", None