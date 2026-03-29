from fastapi import APIRouter, UploadFile, File
import numpy as np
import cv2

from backend.services.face_service import FaceService
from backend.services.attendance_service import AttendanceService
from backend.database.db import get_all_embeddings

router = APIRouter()

face_service = FaceService()
attendance_service = AttendanceService()

@router.post("/recognize")
async def recognize(file: UploadFile = File(...)):
    contents = await file.read()

    np_arr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    faces = face_service.detect(frame)

    db_embeddings = get_all_embeddings()

    results = []

    for face in faces:
        emb = face_service.extract_embedding(face)

        student_id, score = face_service.recognize(emb, db_embeddings)

        if student_id:
            attendance_service.mark_attendance(student_id)

        results.append({
            "student_id": student_id,
            "score": float(score)
        })

    return {"results": results}