from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

# === Response chung (Unified) ===
class ApiResponse(BaseModel):
    status: str = "success"
    message: str
    data: Optional[Any] = None
    timestamp: Optional[datetime] = None

# ====================== STUDENT ======================
class Student(BaseModel):
    id: int
    name: str


class StudentListResponse(ApiResponse):
    data: List[Student]


class StudentDetailResponse(ApiResponse):
    data: Optional[Student] = None


# ====================== ATTENDANCE ======================
class AttendanceRecord(BaseModel):
    id: int
    student_id: int
    name: str
    timestamp: datetime


class AttendanceResponse(ApiResponse):
    data: List[AttendanceRecord]

 # ====================== RECOGNIZE ======================
class RecognizeResult(BaseModel):
    student_id: Optional[int]
    score: float

class RecognizeResponse(BaseModel):
    results: List[RecognizeResult]
    message: Optional[str] = None

class RecognizeResponse(ApiResponse):
    data: List[RecognizeResult]

# ====================== REGISTER ======================
class RegisterResponse(ApiResponse):
    data: Optional[Dict[str, Any]] = None    