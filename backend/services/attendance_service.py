import logging
from backend.database.db import insert_attendance, check_attendance_today

logger = logging.getLogger("face-attendance.attendance_service")


class AttendanceService:
    """Service quản lý điểm danh"""
    
    def mark_attendance(self, student_id):
        """
        Ghi nhận điểm danh cho sinh viên (tránh trùng trong 1 ngày)
        
        Args:
            student_id: ID của sinh viên
            
        Returns:
            bool: True nếu đã ghi nhận, False nếu đã điểm danh hôm nay
        """
        try:
            if not student_id:
                logger.warning("Student ID không hợp lệ")
                return False
            
            # Check xem đã điểm danh hôm nay chưa
            if not check_attendance_today(student_id):
                insert_attendance(student_id)
                logger.info(f"✅ Ghi nhận điểm danh thành công cho sinh viên ID: {student_id}")
                return True
            else:
                logger.info(f"ℹ️ Sinh viên ID {student_id} đã điểm danh hôm nay")
                return False
                
        except Exception as e:
            logger.error(f"❌ Lỗi ghi nhận điểm danh cho sinh viên {student_id}: {str(e)}", exc_info=True)
            raise