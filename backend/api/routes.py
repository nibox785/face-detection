from fastapi import APIRouter, UploadFile, File, HTTPException, status, Form, Query, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
import numpy as np
import cv2
import logging
import csv
import json
import base64
from io import StringIO, BytesIO
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from uuid import uuid4
import jwt
import time

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    HAS_SLOWAPI = True
except ImportError:
    HAS_SLOWAPI = False
    logger_temp = logging.getLogger("face-attendance.routes")
    logger_temp.warning("⚠️ slowapi not installed - run: pip install slowapi")

from backend.services.face_service import FaceService
from backend.services.attendance_service import AttendanceService
from backend.services.register_service import RegisterService

from backend.database.db import (
    get_all_students,
    get_student_by_id,
    get_student_by_name,
    get_student_by_mssv,
    delete_student_and_embedding,
    get_attendance_range,
    get_attendance_by_student,
    get_all_embeddings,
    create_student,
    update_student_name,
    update_student_mssv,
    save_embedding,
    revoke_token,
    cleanup_revoked_tokens,
    is_token_revoked,
)
from backend.database.schemas import (
    RecognizeResponse,
    RecognizeResult,
    RegisterResponse,
    StudentListResponse,
    StudentDetailResponse,
    AttendanceResponse,
    LoginResponse,
    LoginRequest
)

from core.config import (
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    SECRET_KEY,
    ACCESS_TOKEN_EXPIRE_SECONDS,
    SPOOF_REJECT_THRESHOLD,
    SPOOF_SUSPECT_THRESHOLD,
    SPOOF_ADAPTIVE_AREA_START_RATIO,
    SPOOF_ADAPTIVE_MAX_BONUS,
    REALTIME_WS_DETECT_INTERVAL_MS,
    REALTIME_WS_TRACK_TTL_MS,
    REALTIME_WS_RECOGNIZE_COOLDOWN_MS,
)

# ====================== CONFIG ======================
router = APIRouter()
logger = logging.getLogger("face-attendance.routes")

# Rate limiting (prevent DDoS/API abuse)
if HAS_SLOWAPI:
    limiter = Limiter(key_func=get_remote_address)
    logger.info("✅ Rate limiting enabled (slowapi)")
else:
    limiter = None

DATASET_ROOT = Path("dataset")
DATASET_ROOT.mkdir(parents=True, exist_ok=True)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file size
TARGET_REGISTRATION_FRAMES = 10
MIN_ACCEPTED_REGISTRATION_FRAMES = 4
QUALITY_SCORE_THRESHOLD = 0.30
AUTO_MARK_THRESHOLD = 0.66
MANUAL_REVIEW_THRESHOLD = 0.48
SUSPECT_LIVENESS_STRONG_MATCH_DELTA = 0.04

# ====================== SERVICES ======================
face_service = FaceService(threshold=0.68)
attendance_service = AttendanceService()
register_service = RegisterService()

# ====================== CACHE ======================
# Lưu embeddings cache (sẽ được cập nhật từ main.py)
embeddings_cache: List[tuple] = []

def update_embeddings_cache(rebuild_faiss: bool = True):
    """Reload embeddings cache từ database và optionally rebuild FAISS index."""
    global embeddings_cache
    embeddings_cache.clear()
    embeddings_cache.extend(get_all_embeddings())
    logger.info(f"📦 Đã update cache: {len(embeddings_cache)} embeddings")
    
    # Rebuild FAISS index
    if rebuild_faiss:
        try:
            from backend.main import init_faiss_index
            init_faiss_index()
        except Exception as e:
            logger.warning(f"⚠️ Cannot rebuild FAISS index: {str(e)}")


def _append_embeddings_runtime_cache(student_id: int, embeddings: List[np.ndarray]) -> None:
    """Fast-path: update in-memory cache + FAISS without full reload."""
    if not student_id or not embeddings:
        return

    pairs = [(int(student_id), emb) for emb in embeddings if emb is not None]
    if not pairs:
        return

    try:
        embeddings_cache.extend(pairs)
    except Exception:
        # If cache is in an unexpected state, caller can force reload later.
        pass

    # Incrementally add to FAISS if available.
    try:
        from backend.main import faiss_index
        if faiss_index is not None:
            faiss_index.add_embeddings(pairs)
    except Exception as e:
        logger.warning(f"⚠️ Cannot incremental-add to FAISS: {str(e)}")

# ====================== HELPER FUNCTIONS ======================
def validate_image_file(file: UploadFile, max_size: int = MAX_FILE_SIZE) -> bool:
    """Validate image file type and size"""
    # Kiểm tra content_type nếu được cung cấp
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File phải là ảnh")
    
    # Nếu content_type không được cung cấp, kiểm tra extension
    if not file.content_type:
        filename = file.filename or ""
        file_ext = filename.lower().split('.')[-1] if '.' in filename else ""
        if file_ext not in {'jpg', 'jpeg', 'png', 'bmp', 'webp', 'gif'}:
            raise HTTPException(status_code=400, detail="File phải là ảnh (jpg, png, bmp, webp, gif)")
    
    if file.size and file.size > max_size:
        raise HTTPException(
            status_code=413, 
            detail=f"File quá lớn. Tối đa {max_size / 1024 / 1024:.0f}MB"
        )
    return True


def sanitize_student_name(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name.strip())
    return safe.replace(" ", "_") or "student"


def save_dataset_image(student_name: str, filename: str, contents: bytes) -> str:
    safe_name = sanitize_student_name(student_name)
    student_dir = DATASET_ROOT / safe_name
    student_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix.lower() if filename else ".jpg"
    if ext not in IMAGE_EXTENSIONS:
        ext = ".jpg"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_suffix = uuid4().hex[:8]
    destination = student_dir / f"{timestamp}_{unique_suffix}{ext}"
    
    with open(destination, "wb") as f:
        f.write(contents)
    
    return str(destination)


def score_registration_frame(frame: np.ndarray, face_image: np.ndarray, bbox: dict) -> float:
    if frame is None or face_image is None or bbox is None:
        return 0.0

    if frame.size == 0 or face_image.size == 0:
        return 0.0

    gray_face = cv2.cvtColor(face_image, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray_face, cv2.CV_64F).var())
    sharpness_score = min(1.0, sharpness / 180.0)

    brightness = float(np.mean(gray_face))
    brightness_score = max(0.0, 1.0 - abs(brightness - 128.0) / 128.0)

    frame_h, frame_w = frame.shape[:2]
    frame_area = float(frame_h * frame_w)
    face_w = float(max(0, bbox.get("w", 0)))
    face_h = float(max(0, bbox.get("h", 0)))
    face_area = face_w * face_h
    area_ratio = face_area / frame_area if frame_area > 0 else 0.0
    area_score = min(1.0, area_ratio * 7.0)

    # Heuristic tương tự center_weighted_size trong MTCNN: ưu tiên mặt gần trung tâm.
    cx = float(bbox.get("x", 0)) + (face_w / 2.0)
    cy = float(bbox.get("y", 0)) + (face_h / 2.0)
    frame_cx = frame_w / 2.0
    frame_cy = frame_h / 2.0
    dist = float(np.hypot(cx - frame_cx, cy - frame_cy))
    max_dist = float(np.hypot(frame_cx, frame_cy))
    center_score = max(0.0, 1.0 - (dist / max_dist)) if max_dist > 0 else 0.0

    confidence = float(bbox.get("confidence", 0.0))
    confidence_score = min(1.0, max(0.0, confidence))

    score = (
        0.30 * sharpness_score +
        0.20 * brightness_score +
        0.20 * area_score +
        0.15 * center_score +
        0.15 * confidence_score
    )
    return float(max(0.0, min(1.0, score)))


def select_best_face_for_registration(faces_with_bbox: List[tuple], frame_shape: tuple):
    if not faces_with_bbox:
        return None

    frame_h, frame_w = frame_shape[:2]
    frame_area = float(max(1, frame_h * frame_w))
    frame_cx = frame_w / 2.0
    frame_cy = frame_h / 2.0
    max_dist = float(np.hypot(frame_cx, frame_cy)) if (frame_w > 0 and frame_h > 0) else 1.0

    best = None
    best_score = -1.0
    for face_image, bbox in faces_with_bbox:
        face_w = float(max(0, bbox.get("w", 0)))
        face_h = float(max(0, bbox.get("h", 0)))
        area_ratio = (face_w * face_h) / frame_area
        area_score = min(1.0, area_ratio * 7.0)

        cx = float(bbox.get("x", 0)) + (face_w / 2.0)
        cy = float(bbox.get("y", 0)) + (face_h / 2.0)
        dist = float(np.hypot(cx - frame_cx, cy - frame_cy))
        center_score = max(0.0, 1.0 - (dist / max_dist)) if max_dist > 0 else 0.0

        confidence_score = min(1.0, max(0.0, float(bbox.get("confidence", 0.0))))

        candidate_score = (0.45 * confidence_score) + (0.35 * area_score) + (0.20 * center_score)
        if candidate_score > best_score:
            best_score = candidate_score
            best = (face_image, bbox)

    return best


def create_access_token(data: dict, expires_seconds: int = ACCESS_TOKEN_EXPIRE_SECONDS) -> str:
    """Tạo JWT token bằng PyJWT"""
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(seconds=expires_seconds)
    payload.update({"exp": expire, "jti": uuid4().hex})
    
    encoded_jwt = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def verify_access_token(token: str) -> dict:
    """Xác thực JWT token bằng PyJWT"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        now_ts = int(datetime.utcnow().timestamp())
        cleanup_revoked_tokens(now_ts)

        jti = payload.get("jti")
        if not jti:
            raise HTTPException(status_code=401, detail="Token thiếu thông tin định danh")

        if is_token_revoked(str(jti)):
            raise HTTPException(status_code=401, detail="Token đã bị thu hồi")

        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token đã hết hạn")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")
    except Exception:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")


def extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Yêu cầu đăng nhập (Bearer token)")

    return authorization.split(' ', 1)[1]


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

    # Always keep suspect threshold below hard reject threshold.
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

    # In practice DeepFace score semantics can vary between builds. For live
    # attendance, only hard-reject when model also indicates non-real.
    if (not bool(is_real)) and score >= SPOOF_REJECT_THRESHOLD:
        return True, "high_spoof_score", face_area_ratio, suspect_threshold

    if (not bool(is_real)) and score >= suspect_threshold:
        return True, "suspect_non_real", face_area_ratio, suspect_threshold

    return False, "pass_or_uncertain", face_area_ratio, suspect_threshold


def get_current_admin(authorization: Optional[str] = Header(None)) -> dict:
    token = extract_bearer_token(authorization)
    return verify_access_token(token)


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _decode_ws_image_to_frame(image_b64: str) -> np.ndarray:
    if not image_b64:
        raise ValueError("Thiếu dữ liệu ảnh")

    payload = image_b64
    if image_b64.startswith("data:") and "," in image_b64:
        payload = image_b64.split(",", 1)[1]

    raw = base64.b64decode(payload)
    np_arr = np.frombuffer(raw, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Không thể decode ảnh từ websocket payload")
    return frame


def _attach_track_ids_from_hints(results: List[dict], track_hints: List[dict]) -> List[dict]:
    if not results:
        return results

    hints = [
        hint for hint in (track_hints or [])
        if isinstance(hint, dict) and hint.get("track_id")
    ]
    if not hints:
        return results

    used_hint_indexes = set()
    max_match_distance_px = 240.0

    for result in results:
        bbox = result.get("bbox") or {}
        if not bbox:
            continue

        rcx = float(bbox.get("x", 0)) + float(bbox.get("w", 0)) / 2.0
        rcy = float(bbox.get("y", 0)) + float(bbox.get("h", 0)) / 2.0
        best_idx = -1
        best_dist = float("inf")

        for idx, hint in enumerate(hints):
            if idx in used_hint_indexes:
                continue
            hcx = float(hint.get("x", 0)) + float(hint.get("w", 0)) / 2.0
            hcy = float(hint.get("y", 0)) + float(hint.get("h", 0)) / 2.0
            dist = float(np.hypot(rcx - hcx, rcy - hcy))
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

        if best_idx >= 0 and best_dist <= max_match_distance_px:
            used_hint_indexes.add(best_idx)
            result["track_id"] = hints[best_idx].get("track_id")

    return results


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

        # Với crop, không có bbox/frame_shape đầy đủ → dùng gate cơ bản (không adaptive theo area).
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


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _center_of_bbox(bbox: dict) -> tuple[float, float]:
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    w = float(bbox.get("w", 0))
    h = float(bbox.get("h", 0))
    return (x + w / 2.0, y + h / 2.0)


def _match_detections_to_tracks(
    detections: List[dict],
    tracks: List[dict],
    max_center_dist_px: float = 160.0,
) -> tuple[dict[int, int], set[int], set[int]]:
    """
    Greedy center-distance assignment.
    Returns:
      - det_to_track: det_idx -> track_idx
      - used_det_idxs
      - used_track_idxs
    """
    det_centers = [_center_of_bbox(det["bbox"]) for det in detections]
    track_centers = [_center_of_bbox(tr["bbox"]) for tr in tracks]

    pairs = []
    for di, (dcx, dcy) in enumerate(det_centers):
        for ti, (tcx, tcy) in enumerate(track_centers):
            dist = float(np.hypot(dcx - tcx, dcy - tcy))
            if dist <= max_center_dist_px:
                pairs.append((dist, di, ti))
    pairs.sort(key=lambda item: item[0])

    det_to_track: dict[int, int] = {}
    used_det = set()
    used_track = set()
    for dist, di, ti in pairs:
        if di in used_det or ti in used_track:
            continue
        det_to_track[di] = ti
        used_det.add(di)
        used_track.add(ti)

    return det_to_track, used_det, used_track


# session_id -> {"tracks": List[dict], "last_seen_ms": int}
_realtime_sessions: dict[str, dict] = {}


def _create_cv2_tracker():
    """
    Prefer very fast trackers for realtime bbox continuity.
    MOSSE is typically the fastest; fallback to KCF.
    """
    # OpenCV 4.x may expose trackers under cv2.legacy
    legacy = getattr(cv2, "legacy", None)
    if legacy is not None:
        if hasattr(legacy, "TrackerMOSSE_create"):
            return legacy.TrackerMOSSE_create()
        if hasattr(legacy, "TrackerKCF_create"):
            return legacy.TrackerKCF_create()

    if hasattr(cv2, "TrackerMOSSE_create"):
        return cv2.TrackerMOSSE_create()
    if hasattr(cv2, "TrackerKCF_create"):
        return cv2.TrackerKCF_create()

    return None


# ====================== AUTH ======================
@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    if request.username != ADMIN_USERNAME or request.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng")

    access_token = create_access_token({"sub": request.username})
    return LoginResponse(
        status="success",
        message="Đăng nhập thành công",
        data={"access_token": access_token, "token_type": "bearer"}
    )


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Thu hồi JWT hiện tại bằng cách lưu jti vào blacklist bền vững."""
    token = extract_bearer_token(authorization)
    payload = verify_access_token(token)

    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        revoke_token(str(jti), int(exp))

    return {"status": "success", "message": "Đăng xuất thành công"}


@router.get("/auth/verify")
async def verify_auth(authorization: Optional[str] = Header(None)):
    """Frontend dùng endpoint này để kiểm tra token trước khi vào hệ thống."""
    payload = get_current_admin(authorization)
    return {
        "status": "success",
        "message": "Token hợp lệ",
        "data": {
            "username": payload.get("sub", "admin"),
            "expires_at": payload.get("exp")
        }
    }


# ====================== REGISTER ======================
@router.post("/register", response_model=RegisterResponse)
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
        # Keep old behavior available via manual cache reload if needed.
        update_embeddings_cache(rebuild_faiss=False)

        return RegisterResponse(
            status="success",
            message=message,
            data={"student_id": student_id, "name": name}
        )
    else:
        raise HTTPException(status_code=400, detail=message)


@router.post("/dataset/register", response_model=RegisterResponse)
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
        update_embeddings_cache(rebuild_faiss=False)

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


@router.post("/dataset/register-multiple", response_model=RegisterResponse)
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


@router.post("/face/check")
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


# ====================== RECOGNIZE ======================
@router.post("/recognize", response_model=RecognizeResponse)
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
    # ✅ FIX: Kiểm tra auth - nếu không có token/key thì reject
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
            # Token không hợp lệ - reject
            raise
    # Alternatively: Device key validation (for kiosk devices)
    # Có thể thêm logic: elif authorization.startswith('DeviceKey '):  ...
    else:
        # Chỉ chấp nhận Bearer token hiện tại
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


@router.websocket("/ws/recognize")
async def recognize_stream(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    try:
        verify_access_token(token)
    except HTTPException:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    logger.info("WS recognize connected")

    try:
        while True:
            raw_message = await websocket.receive_text()
            payload = json.loads(raw_message)
            msg_type = payload.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": int(datetime.utcnow().timestamp() * 1000)})
                continue

            if msg_type != "frame":
                await websocket.send_json({"type": "error", "message": "Unsupported message type"})
                continue

            frame_id = payload.get("frame_id")
            image_b64 = payload.get("image")
            track_hints = payload.get("track_hints") or []

            try:
                frame = _decode_ws_image_to_frame(image_b64)
                results = run_recognition_on_frame(frame)
                result_dicts = [_model_to_dict(item) for item in results]
                result_dicts = _attach_track_ids_from_hints(result_dicts, track_hints)

                await websocket.send_json({
                    "type": "recognize_result",
                    "frame_id": frame_id,
                    "results": result_dicts,
                })
            except Exception as e:
                logger.error(f"WS recognize frame error: {str(e)}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "frame_id": frame_id,
                    "message": str(e),
                })
    except WebSocketDisconnect:
        logger.info("WS recognize disconnected")
    except Exception as e:
        logger.error(f"WS recognize fatal error: {str(e)}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass


@router.websocket("/ws/realtime/{session_id}")
async def realtime_track_stream(websocket: WebSocket, session_id: str):
    """
    Realtime WS theo session (Mode B: backend detect + track):
    - FE gửi full frame (JPEG base64)
    - Backend detect + assign track_id + (throttle) recognize theo track
    - Backend trả về tracks với bbox + result để FE vẽ overlay liên tục
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    try:
        verify_access_token(token)
    except HTTPException:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    logger.info(f"WS realtime connected session_id={session_id}")

    # Init / attach session tracker state
    session = _realtime_sessions.get(session_id)
    if not session:
        session = {
            "tracks": [],
            "last_seen_ms": _now_ms(),
            "last_detect_ms": 0,
            # Cache student_ids already marked in this WS session to avoid repeated DB checks
            # and to allow the frontend to skip already-marked events in telemetry.
            "attended_student_ids": set(),
        }
        _realtime_sessions[session_id] = session
    tracks: List[dict] = session["tracks"]
    attended_student_ids: set = session.get("attended_student_ids") or set()
    session["attended_student_ids"] = attended_student_ids

    try:
        while True:
            raw_message = await websocket.receive_text()
            payload = json.loads(raw_message)
            msg_type = payload.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": int(datetime.utcnow().timestamp() * 1000)})
                continue

            if msg_type != "frame":
                await websocket.send_json({"type": "error", "message": "Unsupported message type"})
                continue
            frame_id = payload.get("frame_id")
            image_b64 = payload.get("image")

            try:
                now_ms = _now_ms()
                session["last_seen_ms"] = now_ms

                frame = _decode_ws_image_to_frame(image_b64)

                # 1) Update trackers every WS frame to keep bbox smooth.
                for tr in tracks:
                    tracker = tr.get("tracker")
                    if tracker is None:
                        continue
                    try:
                        ok, box = tracker.update(frame)
                        if ok and box is not None:
                            x, y, w, h = box
                            tr["bbox"] = {
                                "x": float(x),
                                "y": float(y),
                                "w": float(w),
                                "h": float(h),
                                "confidence": float(tr.get("bbox", {}).get("confidence", 0.0) if tr.get("bbox") else 0.0),
                            }
                            tr["last_seen_ms"] = now_ms
                    except Exception:
                        # Tracker may fail on some frames; keep last bbox until next detect refresh.
                        pass

                # 2) Run heavy face detection at a lower rate to correct tracker drift and discover new faces.
                detect_interval_ms = max(120, int(REALTIME_WS_DETECT_INTERVAL_MS))
                should_detect = (now_ms - int(session.get("last_detect_ms", 0))) >= detect_interval_ms

                detections: List[dict] = []
                if should_detect:
                    session["last_detect_ms"] = now_ms
                    faces_with_bbox = face_service.detect(frame)
                    for face_img, bbox in faces_with_bbox:
                        detections.append({
                            "face": face_img,
                            "bbox": {
                                "x": bbox.get("x", 0),
                                "y": bbox.get("y", 0),
                                "w": bbox.get("w", 0),
                                "h": bbox.get("h", 0),
                                "confidence": float(bbox.get("confidence", 0.0)),
                            } if bbox else None,
                        })

                # Drop stale tracks
                track_ttl_ms = max(600, int(REALTIME_WS_TRACK_TTL_MS))
                tracks[:] = [
                    tr for tr in tracks
                    if now_ms - int(tr.get("last_seen_ms", now_ms)) <= track_ttl_ms
                ]

                if detections:
                    # Match detections to existing tracks
                    det_to_track, used_det, used_track = _match_detections_to_tracks(detections, tracks)

                    # Update matched tracks (and refresh trackers)
                    for det_idx, tr_idx in det_to_track.items():
                        det = detections[det_idx]
                        tr = tracks[tr_idx]
                        tr["bbox"] = det["bbox"]
                        tr["last_seen_ms"] = now_ms
                        tr["seen_count"] = int(tr.get("seen_count", 0)) + 1
                        tr["face"] = det["face"]

                        tracker = _create_cv2_tracker()
                        if tracker is not None and det.get("bbox"):
                            try:
                                b = det["bbox"]
                                tracker.init(frame, (float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])))
                                tr["tracker"] = tracker
                            except Exception:
                                tr["tracker"] = None

                    # Create new tracks for unmatched detections
                    for det_idx, det in enumerate(detections):
                        if det_idx in used_det:
                            continue
                        tracker = _create_cv2_tracker()
                        if tracker is not None and det.get("bbox"):
                            try:
                                b = det["bbox"]
                                tracker.init(frame, (float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])))
                            except Exception:
                                tracker = None
                        tracks.append({
                            "track_id": f"trk-{uuid4().hex[:10]}",
                            "bbox": det["bbox"],
                            "last_seen_ms": now_ms,
                            "seen_count": 1,
                            "last_recognized_ms": 0,
                            "result": None,
                            "face": det["face"],
                            "tracker": tracker,
                        })

                # Recognition throttle per track
                recognize_cooldown_ms = max(250, int(REALTIME_WS_RECOGNIZE_COOLDOWN_MS))
                outbound_tracks = []
                for tr in tracks:
                    face_img = tr.get("face")
                    per_track_cooldown_ms = int(tr.get("recognize_cooldown_ms", 0) or 0)
                    effective_cooldown_ms = max(recognize_cooldown_ms, per_track_cooldown_ms)
                    should_recognize = (
                        face_img is not None
                        and now_ms - int(tr.get("last_recognized_ms", 0)) >= effective_cooldown_ms
                    )

                    if should_recognize:
                        result_model = run_recognition_on_face_crop(face_img)
                        tr["last_recognized_ms"] = now_ms
                        result_dict = _model_to_dict(result_model) if result_model else None

                        # If this student was already marked in this session (or earlier today),
                        # annotate the result and increase cooldown to reduce repeated work.
                        if isinstance(result_dict, dict) and result_dict.get("student_id"):
                            sid = result_dict.get("student_id")
                            if sid in attended_student_ids:
                                result_dict["attendance_status"] = "ALREADY_MARKED"
                                # Slow down repeated recognitions for already-marked tracks.
                                tr["recognize_cooldown_ms"] = max(int(tr.get("recognize_cooldown_ms", 0) or 0), 3000)
                            else:
                                # Mark attendance once per session for this student.
                                try:
                                    marked = attendance_service.mark_attendance(sid)
                                except Exception:
                                    marked = False
                                attended_student_ids.add(sid)
                                result_dict["attendance_status"] = "MARKED" if marked else "ALREADY_MARKED"
                                # After first mark, further recognitions can be slower.
                                tr["recognize_cooldown_ms"] = max(int(tr.get("recognize_cooldown_ms", 0) or 0), 2500)

                        tr["result"] = result_dict

                    # Do not keep raw face in memory across ticks
                    tr["face"] = None

                    outbound_tracks.append({
                        "track_id": tr.get("track_id"),
                        "bbox": tr.get("bbox"),
                        "result": tr.get("result"),
                        "last_seen_ms": tr.get("last_seen_ms"),
                    })

                await websocket.send_json({
                    "type": "frame_result",
                    "session_id": session_id,
                    "frame_id": frame_id,
                    "tracks": outbound_tracks,
                })
            except Exception as e:
                logger.error(f"WS realtime frame error: {str(e)}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "session_id": session_id,
                    "frame_id": frame_id,
                    "message": str(e),
                })
    except WebSocketDisconnect:
        logger.info(f"WS realtime disconnected session_id={session_id}")
    except Exception as e:
        logger.error(f"WS realtime fatal error session_id={session_id}: {str(e)}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass
    finally:
        # Best-effort cleanup: drop empty/idle sessions
        try:
            session = _realtime_sessions.get(session_id)
            if session:
                session["tracks"] = []
                session["last_seen_ms"] = _now_ms()
                session["attended_student_ids"] = set()
        except Exception:
            pass

# ====================== LIVENESS DETECTION ======================
@router.post("/face/liveness-check")
async def liveness_check(file: UploadFile = File(...)):
    """Kiểm tra liveness (chống spoofing) - Rất quan trọng cho demo"""
    validate_image_file(file)
    
    try:
        contents = await file.read()
        np_arr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="Không thể đọc được file ảnh")

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
    
# ====================== MANAGEMENT API ======================
@router.get("/students", response_model=StudentListResponse)
async def get_students(authorization: Optional[str] = Header(None)):
    get_current_admin(authorization)
    students = get_all_students()
    return StudentListResponse(
        status="success",
        message="Lấy danh sách sinh viên thành công",
        data=students
    )


@router.get("/students/{student_id}", response_model=StudentDetailResponse)
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


@router.put("/students/{student_id}", response_model=StudentDetailResponse)
async def update_student(
    student_id: int,
    name: str = Form(...),
    authorization: Optional[str] = Header(None)
):
    """Cập nhật tên sinh viên"""
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


@router.get("/attendance", response_model=AttendanceResponse)
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


@router.get("/attendance/export")
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
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Attendance', index=False)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=attendance_report.xlsx"}
    )


@router.delete("/students/{student_id}")
async def delete_student(student_id: int, authorization: Optional[str] = Header(None)):
    get_current_admin(authorization)
    
    success = delete_student_and_embedding(student_id)
    if success:
        update_embeddings_cache()
        
        return {"status": "success", "message": f"Đã xóa sinh viên ID {student_id} và dữ liệu liên quan"}
    
    raise HTTPException(status_code=400, detail="Xóa thất bại")