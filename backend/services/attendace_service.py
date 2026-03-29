from backend.database.db import insert_attendance, check_attendance_today


class AttendanceService:

    def mark_attendance(self, student_id):
        # tránh điểm danh trùng
        if not check_attendance_today(student_id):
            insert_attendance(student_id)
            return True
        return False