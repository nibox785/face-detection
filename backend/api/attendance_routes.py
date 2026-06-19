"""
Attendance management routes: GET /students, GET /students/{id}, PUT /students/{id}, DELETE /students/{id}, GET /attendance, GET /attendance/export
"""
import logging
from typing import Optional
from io import BytesIO

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.database.db import (
    get_all_students,
    get_student_by_id,
    update_student_name,
    delete_student_and_embedding,
    get_attendance_range,
    get_attendance_by_student,
)
from backend.database.schemas import (
    StudentListResponse,
    StudentDetailResponse,
    AttendanceResponse,
)
from .auth_routes import get_current_admin
from .common import update_embeddings_cache

logger = logging.getLogger("face-attendance.attendance_routes")

attendance_router = APIRouter(prefix="", tags=["attendance"])


@attendance_router.get("/students", response_model=StudentListResponse)
async def get_students(authorization: Optional[str] = Header(None)):
    get_current_admin(authorization)
    students = get_all_students()
    return StudentListResponse(
        status="success",
        message="Lấy danh sách sinh viên thành công",
        data=students
    )


@attendance_router.get("/students/{student_id}", response_model=StudentDetailResponse)
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


@attendance_router.put("/students/{student_id}", response_model=StudentDetailResponse)
async def update_student(
    student_id: int,
    name: str = None,
    authorization: Optional[str] = Header(None)
):
    """Cập nhật tên sinh viên"""
    from fastapi import Form
    get_current_admin(authorization)
    
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Tên sinh viên không được để trống")
    
    # Check student exists
    student = get_student_by_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên")
    
    # Update logic
    try:
        updated = update_student_name(student_id, name)
        if not updated:
            raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên")
        
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


@attendance_router.get("/attendance", response_model=AttendanceResponse)
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


@attendance_router.get("/attendance/export")
async def export_attendance(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None)
):
    get_current_admin(authorization)
    records = get_attendance_range(start_date, end_date)

    # Tạo DataFrame từ records
    import pandas as pd
    df = pd.DataFrame(records)

    # Đổi tên cột cho đẹp
    df = df.rename(columns={
        'id': 'ID',
        'student_id': 'Student_ID',
        'name': 'Name',
        'timestamp': 'Timestamp'
    })

    # Tạo Excel in-memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Attendance', index=False)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=attendance_report.xlsx"}
    )


@attendance_router.delete("/students/{student_id}")
async def delete_student(student_id: int, authorization: Optional[str] = Header(None)):
    get_current_admin(authorization)
    
    success = delete_student_and_embedding(student_id)
    if success:
        update_embeddings_cache()
        
        return {"status": "success", "message": f"Đã xóa sinh viên ID {student_id} và dữ liệu liên quan"}
    
    raise HTTPException(status_code=400, detail="Xóa thất bại")
