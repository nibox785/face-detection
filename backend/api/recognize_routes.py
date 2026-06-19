"""
Recognition routes: POST /recognize, POST /face/liveness-check
"""
import logging
from typing import Optional, List, Tuple
import json
from datetime import datetime

import cv2
import numpy as np
from fastapi import APIRouter, Header, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosedOK

from backend.services.face_service import FaceService
from backend.services.attendance_service import AttendanceService
from backend.database.db import get_student_by_id
from backend.database.schemas import RecognizeResponse, RecognizeResult
from core.config import (
    SPOOF_REJECT_THRESHOLD,
    SPOOF_SUSPECT_THRESHOLD,
    SPOOF_ADAPTIVE_AREA_START_RATIO,
    SPOOF_ADAPTIVE_MAX_BONUS,
)
from .auth_routes import verify_access_token, extract_bearer_token
from .common import (
    validate_image_file,
    _decode_ws_image_to_frame,
    _model_to_dict,
    _attach_track_ids_from_hints,
    embeddings_cache,
    AUTO_MARK_THRESHOLD,
    MANUAL_REVIEW_THRESHOLD,
    SUSPECT_LIVENESS_STRONG_MATCH_DELTA,
)

logger = logging.getLogger("face-attendance.recognize_routes")

recognize_router = APIRouter(prefix="", tags=["recognize"])

# ====================== SERVICES ======================
face_service = FaceService(threshold=0.68)
attendance_service = AttendanceService()


def _compute_face_area_ratio(bbox: Optional[dict], frame_shape: Optional[Tuple[int, ...]]) -> float:
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


def should_reject_liveness(
    is_real: bool,
    spoof_score: float,
    bbox: Optional[dict] = None,
    frame_shape: Optional[Tuple[int, ...]] = None,
) -> tuple[bool, str, float, float]:
    """
    Two-stage anti-spoof gate to reduce false reject bursts at session start:
    1) Hard reject if spoof_score is very high.
    2) Suspect reject only when model says non-real AND score is above suspect threshold.
    """
    try:
        score = float(spoof_score)
    except (TypeError, ValueError):
        score = 1.0

    face_area_ratio = _compute_face_area_ratio(bbox, frame_shape)
    suspect_threshold = _adaptive_suspect_threshold(face_area_ratio)

    if (not bool(is_real)) and score >= SPOOF_REJECT_THRESHOLD:
        return True, "high_spoof_score", face_area_ratio, suspect_threshold

    if (not bool(is_real)) and score >= suspect_threshold:
        return True, "suspect_non_real", face_area_ratio, suspect_threshold

    return False, "pass_or_uncertain", face_area_ratio, suspect_threshold


def run_recognition_on_frame(frame: np.ndarray) -> List[RecognizeResult]:
    faces_with_bbox = face_service.detect(frame)
    if not faces_with_bbox:
        return []

    logger.info(f"Phát hiện {len(faces_with_bbox)} khuôn mặt")
    results: List[RecognizeResult] = []
    student_name_cache = {}

    for face_image, bbox in faces_with_bbox:
        try:
            liveness_penalty = False
            liveness_reject_reason = None

            # === LIVENESS DETECTION ===
            embedding, is_real, spoof_score = face_service.get_embedding_with_liveness(face_image)

            should_reject, reject_reason, face_area_ratio, suspect_threshold = should_reject_liveness(
                is_real,
                spoof_score,
                bbox=bbox,
                frame_shape=frame.shape,
            )
            if should_reject and reject_reason == "high_spoof_score":
                results.append(
                    RecognizeResult(
                        student_id=None,
                        name="Spoof Detected",
                        score=0.0,
                        decision="REJECT",
                        liveness={
                            "is_real": False,
                            "spoof_score": round(float(spoof_score), 4),
                            "reject_reason": reject_reason,
                            "face_area_ratio": round(float(face_area_ratio), 4),
                            "suspect_threshold": round(float(suspect_threshold), 4),
                            "hard_threshold": round(float(SPOOF_REJECT_THRESHOLD), 4),
                        },
                        bbox={
                            "x": bbox.get("x", 0),
                            "y": bbox.get("y", 0),
                            "w": bbox.get("w", 0),
                            "h": bbox.get("h", 0),
                            "confidence": float(bbox.get("confidence", 0.0))
                        } if bbox else None
                    )
                )
                logger.warning(
                    f"🚨 Phát hiện spoof attack! Score: {float(spoof_score):.4f}, reason={reject_reason}"
                )
                continue

            if should_reject and reject_reason == "suspect_non_real":
                liveness_penalty = True
                liveness_reject_reason = reject_reason
                logger.info(
                    "Liveness suspect frame: keep recognition path with decision penalty "
                    f"(score={float(spoof_score):.4f}, area={face_area_ratio:.4f})"
                )

            # Nếu là người thật → tiếp tục recognize bình thường (với FAISS nếu có)
            try:
                from backend.main import faiss_index as shared_faiss_index
                use_faiss = shared_faiss_index is not None and shared_faiss_index.is_built
            except Exception:
                shared_faiss_index = None
                use_faiss = False

            student_id, score = face_service.recognize(
                embedding,
                embeddings_cache,
                use_faiss=use_faiss,
                faiss_index=shared_faiss_index,
            )

            top_candidates_raw = face_service.recognize_topk(
                embedding,
                embeddings_cache,
                top_k=3,
            )

        except Exception as e:
            logger.error(f"Lỗi xử lý face với liveness: {str(e)}")
            continue

        top_candidates = []
        for rank, (cand_student_id, cand_score) in enumerate(top_candidates_raw, start=1):
            candidate_name = "Unknown"
            if cand_student_id in student_name_cache:
                candidate_name = student_name_cache[cand_student_id]
            else:
                student_candidate = get_student_by_id(cand_student_id)
                if student_candidate:
                    candidate_name = student_candidate.get("name", "Unknown")
                student_name_cache[cand_student_id] = candidate_name

            top_candidates.append({
                "rank": rank,
                "student_id": cand_student_id,
                "name": candidate_name,
                "score": round(float(cand_score), 4),
            })

        student_name = "Unknown"
        decision = "REJECT"

        if score >= AUTO_MARK_THRESHOLD and student_id:
            if liveness_penalty:
                strong_match_threshold = AUTO_MARK_THRESHOLD + SUSPECT_LIVENESS_STRONG_MATCH_DELTA
                decision = "AUTO_MARK" if score >= strong_match_threshold else "MANUAL_REVIEW"
            else:
                decision = "AUTO_MARK"
        elif score >= MANUAL_REVIEW_THRESHOLD:
            decision = "MANUAL_REVIEW"

        if student_id:
            attendance_service.mark_attendance(student_id)
            student = get_student_by_id(student_id)
            student_name = student['name'] if student else "Unknown"
            logger.info(f"Điểm danh thành công - Student ID: {student_id} | Name: {student_name} | Score: {score:.4f}")

        results.append(
            RecognizeResult(
                student_id=student_id,
                name=student_name,
                score=round(float(score), 4),
                top_candidates=top_candidates,
                liveness={
                    "is_real": bool(is_real),
                    "spoof_score": round(float(spoof_score), 4),
                    "reject_reason": liveness_reject_reason,
                    "face_area_ratio": round(_compute_face_area_ratio(bbox, frame.shape), 4),
                    "suspect_threshold": round(
                        _adaptive_suspect_threshold(_compute_face_area_ratio(bbox, frame.shape)),
                        4,
                    ),
                    "hard_threshold": round(float(SPOOF_REJECT_THRESHOLD), 4),
                },
                decision=decision,
                bbox={
                    "x": bbox.get("x", 0),
                    "y": bbox.get("y", 0),
                    "w": bbox.get("w", 0),
                    "h": bbox.get("h", 0),
                    "confidence": float(bbox.get("confidence", 0.0))
                } if bbox else None
            )
        )

    return results


def run_recognition_on_face_crop(face_image: np.ndarray) -> Optional[RecognizeResult]:
    """
    Nhận diện trực tiếp trên face crop (không chạy detect).
    Dùng cho realtime WS theo track_id (frontend giữ bbox local).
    """
    if face_image is None or getattr(face_image, "size", 0) == 0:
        return None

    try:
        liveness_penalty = False
        liveness_reject_reason = None

        embedding, is_real, spoof_score = face_service.get_embedding_with_liveness(face_image)

        should_reject, reject_reason, face_area_ratio, suspect_threshold = should_reject_liveness(
            is_real,
            spoof_score,
            bbox=None,
            frame_shape=None,
        )

        if should_reject and reject_reason == "high_spoof_score":
            return RecognizeResult(
                student_id=None,
                name="Spoof Detected",
                score=0.0,
                decision="REJECT",
                liveness={
                    "is_real": False,
                    "spoof_score": round(float(spoof_score), 4),
                    "reject_reason": reject_reason,
                    "face_area_ratio": round(float(face_area_ratio), 4),
                    "suspect_threshold": round(float(suspect_threshold), 4),
                    "hard_threshold": round(float(SPOOF_REJECT_THRESHOLD), 4),
                },
                bbox=None,
            )

        if should_reject and reject_reason == "suspect_non_real":
            liveness_penalty = True
            liveness_reject_reason = reject_reason

        try:
            from backend.main import faiss_index as shared_faiss_index
            use_faiss = shared_faiss_index is not None and shared_faiss_index.is_built
        except Exception:
            shared_faiss_index = None
            use_faiss = False

        student_id, score = face_service.recognize(
            embedding,
            embeddings_cache,
            use_faiss=use_faiss,
            faiss_index=shared_faiss_index,
        )

        top_candidates_raw = face_service.recognize_topk(
            embedding,
            embeddings_cache,
            top_k=3,
        )
    except Exception as e:
        logger.error(f"Lỗi recognize trên face crop: {str(e)}", exc_info=True)
        return None

    student_name_cache = {}
    top_candidates = []
    for rank, (cand_student_id, cand_score) in enumerate(top_candidates_raw, start=1):
        candidate_name = "Unknown"
        if cand_student_id in student_name_cache:
            candidate_name = student_name_cache[cand_student_id]
        else:
            student_candidate = get_student_by_id(cand_student_id)
            if student_candidate:
                candidate_name = student_candidate.get("name", "Unknown")
            student_name_cache[cand_student_id] = candidate_name

        top_candidates.append({
            "rank": rank,
            "student_id": cand_student_id,
            "name": candidate_name,
            "score": round(float(cand_score), 4),
        })

    student_name = "Unknown"
    decision = "REJECT"

    if score >= AUTO_MARK_THRESHOLD and student_id:
        if liveness_penalty:
            strong_match_threshold = AUTO_MARK_THRESHOLD + SUSPECT_LIVENESS_STRONG_MATCH_DELTA
            decision = "AUTO_MARK" if score >= strong_match_threshold else "MANUAL_REVIEW"
        else:
            decision = "AUTO_MARK"
    elif score >= MANUAL_REVIEW_THRESHOLD:
        decision = "MANUAL_REVIEW"

    if student_id:
        attendance_service.mark_attendance(student_id)
        student = get_student_by_id(student_id)
        student_name = student["name"] if student else "Unknown"

    return RecognizeResult(
        student_id=student_id,
        name=student_name,
        score=round(float(score), 4),
        top_candidates=top_candidates,
        liveness={
            "is_real": bool(is_real),
            "spoof_score": round(float(spoof_score), 4),
            "reject_reason": liveness_reject_reason,
            "face_area_ratio": round(float(face_area_ratio), 4),
            "suspect_threshold": round(float(suspect_threshold), 4),
            "hard_threshold": round(float(SPOOF_REJECT_THRESHOLD), 4),
        },
        decision=decision,
        bbox=None,
    )


@recognize_router.post("/recognize", response_model=RecognizeResponse)
async def recognize(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """
    Nhận diện khuôn mặt và điểm danh (đòi hỏi auth token hoặc device key).
    
    Bảo vệ:
    - Yêu cầu Bearer token hoặc Authorization header (device key)
    - Rate limited: 60 req/min per IP để chống DDoS/spam
    - Được dùng bởi kiosk/app client sau khi xác thực quản trị
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Truy cập /recognize cần authorization header (Bearer token hoặc device key)"
        )
    
    # Try to validate as JWT token (admin session)
    if authorization.startswith('Bearer '):
        try:
            token = authorization.split(' ', 1)[1]
            verify_access_token(token)
            logger.debug(f"✅ Recognize request authorized via JWT token")
        except HTTPException:
            raise
    else:
        raise HTTPException(
            status_code=401,
            detail="Authorization header phải là Bearer token"
        )
    
    logger.info(f"Recognize request - File: {file.filename}")

    # Validate file
    validate_image_file(file)

    try:
        contents = await file.read()
        np_arr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Không thể đọc được file ảnh")

        results = run_recognition_on_frame(frame)

        return RecognizeResponse(
            status="success",
            message=f"Đã xử lý {len(results)} khuôn mặt.",
            data=results
        )

    except Exception as e:
        logger.error(f"Lỗi recognize: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi server khi xử lý nhận diện")


@recognize_router.post("/face/liveness-check")
async def liveness_check(file: UploadFile = File(...)):
    """Kiểm tra liveness (chống spoofing) - Rất quan trọng cho demo"""
    validate_image_file(file)
    
    try:
        contents = await file.read()
        np_arr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Không thể đọc được file ảnh")

        from .register_routes import select_best_face_for_registration, score_registration_frame

        faces_with_bbox = face_service.detect(frame)
        
        if not faces_with_bbox:
            return {
                "status": "error",
                "message": "Không phát hiện được khuôn mặt nào trong ảnh."
            }

        # Chỉ lấy khuôn mặt tốt nhất
        best_face = select_best_face_for_registration(faces_with_bbox, frame.shape)
        if not best_face:
            return {
                "status": "error",
                "message": "Không thể xử lý khuôn mặt"
            }

        face_image, bbox = best_face
        
        # Gọi hàm liveness mới
        embedding, is_real, spoof_score = face_service.get_embedding_with_liveness(face_image)

        should_reject, reject_reason, face_area_ratio, suspect_threshold = should_reject_liveness(
            is_real,
            spoof_score,
            bbox=bbox,
            frame_shape=frame.shape,
        )
        is_live_pass = not should_reject

        return {
            "status": "success",
            "message": "Liveness check completed",
            "data": {
                "is_real": is_live_pass,
                "spoof_score": round(float(spoof_score), 4),
                "reject_reason": reject_reason if should_reject else None,
                "face_area_ratio": round(float(face_area_ratio), 4),
                "suspect_threshold": round(float(suspect_threshold), 4),
                "hard_threshold": round(float(SPOOF_REJECT_THRESHOLD), 4),
                "verdict": "✅ Người thật" if is_live_pass else "❌ Có dấu hiệu giả mạo (ảnh/video/mask)",
                "recommendation": "Vui lòng nhìn thẳng camera và nháy mắt nếu bị từ chối" if not is_live_pass else None,
                "bbox": bbox
            }
        }

    except Exception as e:
        logger.error(f"Lỗi liveness_check: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi server khi kiểm tra liveness")
