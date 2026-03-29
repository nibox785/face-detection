import logging
import numpy as np
from typing import Optional, Tuple

from backend.database.db import save_embedding, get_connection
from backend.services.face_service import FaceService

logger = logging.getLogger("face-attendance.register_service")


class RegisterService:
    def __init__(self):
        self.face_service = FaceService(threshold=0.7)
        logger.info("RegisterService được khởi tạo")

    def register_student(self, name: str, file) -> Tuple[bool, str, Optional[int]]:
        """
        Đăng ký sinh viên mới:
        - Nhận tên + ảnh
        - Detect face
        - Extract embedding
        - Lưu vào database
        """
        try:
            # Đọc file ảnh
            contents = file.file.read() if hasattr(file, 'file') else file.read()
            np_arr = np.frombuffer(contents, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                return False, "Không thể đọc file ảnh", None

            # Detect faces
            faces = self.face_service.detect(frame)
            if not faces:
                return False, "Không phát hiện được khuôn mặt nào trong ảnh", None

            if len(faces) > 1:
                logger.warning(f"Phát hiện {len(faces)} khuôn mặt khi register. Chỉ lấy khuôn mặt đầu tiên.")
            
            # Lấy khuôn mặt đầu tiên (thường là rõ nhất)
            face_image = faces[0]

            # Extract embedding
            embedding = self.face_service.extract_embedding(face_image)

            # Lưu sinh viên vào bảng students
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO students (name) VALUES (?)", (name,))
            student_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # Lưu embedding
            save_embedding(student_id, embedding)

            logger.info(f"✅ Đăng ký thành công - Student ID: {student_id} | Name: {name}")
            return True, "Đăng ký sinh viên thành công", student_id

        except Exception as e:
            logger.error(f"Lỗi khi đăng ký sinh viên: {str(e)}", exc_info=True)
            return False, f"Lỗi server: {str(e)}", None