"""
Registration routes: POST /register, POST /dataset/register, POST /dataset/register-multiple, POST /face/check
"""
import logging
from typing import Optional, List
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from io import BytesIO

import cv2
import numpy as np
from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form

from backend.services.face_service import FaceService
from backend.services.register_service import RegisterService
from backend.database.db import (
    get_student_by_name,
    get_student_by_mssv,
    create_student,
    update_student_mssv,
    save_embedding,
    delete_student_and_embedding,
    get_all_embeddings,
)
from backend.database.schemas import RegisterResponse
from core.config import (
    SPOOF_REJECT_THRESHOLD,
    SPOOF_SUSPECT_THRESHOLD,
    SPOOF_ADAPTIVE_AREA_START_RATIO,
    SPOOF_ADAPTIVE_MAX_BONUS,
)
from .auth_routes import get_current_admin
from .common import (
    validate_image_file,
    sanitize_student_name,
    save_dataset_image,
    score_registration_frame,
    select_best_face_for_registration,
    _append_embeddings_runtime_cache,
    MAX_FILE_SIZE,
    IMAGE_EXTENSIONS,
    TARGET_REGISTRATION_FRAMES,
    MIN_ACCEPTED_REGISTRATION_FRAMES,
    QUALITY_SCORE_THRESHOLD,
)

logger = logging.getLogger("face-attendance.register_routes")

register_router = APIRouter(prefix="", tags=["register"])

# ====================== SERVICES ======================
face_service = FaceService(threshold=0.68)
register_service = RegisterService()


def _compute_face_area_ratio(bbox: Optional[dict], frame_shape: Optional[tuple]) -> float:
    if not bbox or not frame_shape or len(frame_shape) < 2:
        return 0.0

    frame_h, frame_w = frame_shape[:2]
    frame_area = float(max(1, frame_h * frame_w))
    face_w = float(max(0, bbox.get("w", 0)))
    face_h = float(max(0, bbox.get("h", 0)))
    return float((face_w * face_h) / frame_area)


def _adaptive_suspect_threshold(face_area_ratio: float) -> float:
    if face_area_ratio <= SPOOF_ADAPTIVE_AREA_START_RATIO:
        return float(SPOOF_SUSPECT_THRESHOLD)

    bonus = min(
        float(SPOOF_ADAPTIVE_MAX_BONUS),
        max(0.0, (face_area_ratio - SPOOF_ADAPTIVE_AREA_START_RATIO) * 0.8),
    )

    upper_bound = max(float(SPOOF_SUSPECT_THRESHOLD), float(SPOOF_REJECT_THRESHOLD) - 0.02)
    return float(min(upper_bound, float(SPOOF_SUSPECT_THRESHOLD) + bonus))


@register_router.post("/register", response_model=RegisterResponse)
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

    success, message, student_id = register_service.register_student(name, file=file)

    if success:
        # Fast-path: avoid full reload/rebuild per registration.
        try:
            from backend.api.common import update_embeddings_cache
            update_embeddings_cache(rebuild_faiss=False)
        except Exception:
            pass

        return RegisterResponse(
            status="success",
            message=message,
            data={"student_id": student_id, "name": name}
        )
    else:
        raise HTTPException(status_code=400, detail=message)


@register_router.post("/dataset/register", response_model=RegisterResponse)
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
            if mssv and mssv.strip() and not existing.get("mssv"):
                update_student_mssv(existing["id"], mssv)
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

        # Fast-path: avoid full reload/rebuild per registration.
        try:
            from backend.api.common import update_embeddings_cache
            update_embeddings_cache(rebuild_faiss=False)
        except Exception:
            pass

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


@register_router.post("/dataset/register-multiple", response_model=RegisterResponse)
async def register_dataset_multiple(
    name: str = Form(...),
    mssv: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    authorization: Optional[str] = Header(None)
):
    """Đăng ký bằng nhiều góc mặt và trích xuất embedding trong quá trình đăng ký"""
    try:
        get_current_admin(authorization)

        if not name or not name.strip():
            raise HTTPException(status_code=400, detail="Tên sinh viên không được để trống")

        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="Phải gửi ảnh đăng ký")

        if len(files) < TARGET_REGISTRATION_FRAMES:
            raise HTTPException(
                status_code=400,
                detail=f"Cần ít nhất {TARGET_REGISTRATION_FRAMES} ảnh theo các góc mặt để đăng ký"
            )

        registration_files = files[:TARGET_REGISTRATION_FRAMES]
        if len(files) > TARGET_REGISTRATION_FRAMES:
            logger.info(
                f"Nhận {len(files)} ảnh, chỉ xử lý {TARGET_REGISTRATION_FRAMES} ảnh đầu tiên theo quy trình đăng ký"
            )

        logger.info(
            f"Dataset register múltiplo cho sinh viên: {name}, MSSV: {mssv}, "
            f"Số ảnh nhận: {len(files)}, Số ảnh xử lý: {len(registration_files)}"
        )

        # Validate all files
        for file in registration_files:
            validate_image_file(file)

        buffered_inputs = []
        for idx, file in enumerate(registration_files):
            contents = await file.read()
            buffered_inputs.append({
                "index": idx,
                "filename": file.filename or f"{name}_{idx + 1}.jpg",
                "contents": contents,
            })

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
            for item in buffered_inputs:
                save_dataset_image(name, item["filename"], item["contents"])
            return RegisterResponse(
                status="success",
                message=(
                    f"Sinh viên đã tồn tại. {len(registration_files)} ảnh theo quy trình "
                    "đăng ký được lưu vào dataset"
                ),
                data={"student_id": existing["id"], "name": name, "mssv": mssv}
            )

        # Đăng ký mới: trích xuất embedding trực tiếp từ từng ảnh bước đăng ký.
        student_id = create_student(name, mssv)
        accepted_frames = 0
        rejected_frames = 0
        rejected_no_face = 0
        rejected_low_quality = 0
        rejected_embedding_error = 0
        extracted_candidates: List[dict] = []

        for item in buffered_inputs:
            contents = item["contents"]
            
            # Trích xuất embedding
            np_arr = np.frombuffer(contents, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame is None:
                logger.warning(f"Không thể đọc file ảnh: {item['filename']}")
                continue

            faces_with_bbox = face_service.detect(frame)
            
            if not faces_with_bbox:
                logger.warning(f"Không phát hiện khuôn mặt trong {item['filename']}")
                rejected_frames += 1
                rejected_no_face += 1
                continue

            # Ưu tiên khuôn mặt có confidence/diện tích/vị trí tốt nhất.
            best_face = select_best_face_for_registration(faces_with_bbox, frame.shape)
            if not best_face:
                continue

            face_image, bbox = best_face
            quality_score = score_registration_frame(frame, face_image, bbox)
            if quality_score < QUALITY_SCORE_THRESHOLD:
                logger.info(f"Bỏ frame chất lượng thấp: {item['filename']} | score={quality_score:.3f}")
                rejected_frames += 1
                rejected_low_quality += 1
                continue

            try:
                embedding = face_service.extract_embedding(face_image)
            except Exception:
                rejected_frames += 1
                rejected_embedding_error += 1
                continue

            extracted_candidates.append({
                "index": item["index"],
                "embedding": embedding,
                "contents": contents,
                "filename": item["filename"],
                "score": quality_score,
            })

        # Fallback: nếu lọc quality quá chặt nhưng vẫn detect được mặt, thử trích xuất từ các frame còn lại.
        if len(extracted_candidates) < MIN_ACCEPTED_REGISTRATION_FRAMES:
            logger.info(
                f"Kích hoạt fallback đăng ký: extracted={len(extracted_candidates)} < {MIN_ACCEPTED_REGISTRATION_FRAMES}"
            )
            for item in buffered_inputs:
                if any(c["index"] == item["index"] for c in extracted_candidates):
                    continue

                contents = item["contents"]
                np_arr = np.frombuffer(contents, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                faces_with_bbox = face_service.detect(frame)
                if not faces_with_bbox:
                    continue

                best_face = select_best_face_for_registration(faces_with_bbox, frame.shape)
                if not best_face:
                    continue

                face_image, bbox = best_face
                try:
                    embedding = face_service.extract_embedding(face_image)
                except Exception:
                    continue

                extracted_candidates.append({
                    "index": item["index"],
                    "embedding": embedding,
                    "contents": contents,
                    "filename": item["filename"],
                    "score": score_registration_frame(frame, face_image, bbox),
                })

                if len(extracted_candidates) >= TARGET_REGISTRATION_FRAMES:
                    break

        if len(extracted_candidates) == 0:
            delete_student_and_embedding(student_id)
            raise HTTPException(
                status_code=400,
                detail=(
                    "Không thể trích xuất đặc trưng khuôn mặt từ ảnh đăng ký. "
                    f"No-face: {rejected_no_face}, Low-quality: {rejected_low_quality}, "
                    f"Embedding-error: {rejected_embedding_error}."
                )
            )

        extracted_candidates.sort(key=lambda item: item["score"], reverse=True)
        selected_candidates = extracted_candidates[:TARGET_REGISTRATION_FRAMES]

        for candidate in selected_candidates:
            save_embedding(student_id, candidate["embedding"])
            save_dataset_image(name, candidate["filename"], candidate["contents"])
            accepted_frames += 1

        if accepted_frames < MIN_ACCEPTED_REGISTRATION_FRAMES:
            delete_student_and_embedding(student_id)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Chất lượng ảnh chưa đủ ổn định ({accepted_frames}/{TARGET_REGISTRATION_FRAMES} ảnh đạt). "
                    f"Cần ít nhất {MIN_ACCEPTED_REGISTRATION_FRAMES} ảnh đạt để đăng ký an toàn"
                )
            )

        # Fast-path: update runtime cache + incremental FAISS add for new embeddings.
        try:
            _append_embeddings_runtime_cache(student_id, [c["embedding"] for c in selected_candidates if c.get("embedding") is not None])
        except Exception:
            pass

        logger.info(
            f"✅ Đăng ký múltiplo thành công - Student ID: {student_id} | Name: {name} | "
            f"Frames accepted: {accepted_frames} / {TARGET_REGISTRATION_FRAMES} | "
            f"Rejected: {rejected_frames} (no_face={rejected_no_face}, low_quality={rejected_low_quality}, embedding_error={rejected_embedding_error})"
        )

        return RegisterResponse(
            status="success",
            message=(
                f"Đăng ký thành công với {accepted_frames}/{TARGET_REGISTRATION_FRAMES} góc mặt đạt chất lượng. "
                "Đặc trưng khuôn mặt đã được trích xuất trong quá trình đăng ký"
            ),
            data={"student_id": student_id, "name": name, "mssv": mssv}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Lỗi không xác định khi đăng ký múltiplo '{name}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")


@register_router.post("/face/check")
async def check_face(file: UploadFile = File(...)):
    """Kiểm tra nhanh ảnh hiện tại có phát hiện được khuôn mặt hay không."""
    validate_image_file(file)

    try:
        contents = await file.read()
        np_arr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Không thể đọc được file ảnh")

        faces_with_bbox = face_service.detect(frame)
        faces = []
        for face_image, bbox in faces_with_bbox:
            faces.append({
                "bbox": bbox,
                "quality_score": round(score_registration_frame(frame, face_image, bbox), 4),
            })

        return {
            "status": "success",
            "message": "Đã kiểm tra khuôn mặt",
            "data": {
                "face_count": len(faces),
                "faces": faces,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi check_face: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi server khi kiểm tra khuôn mặt")
