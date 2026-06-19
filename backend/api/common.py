"""
Shared helper functions, constants, and configuration for all API routes.
This module contains:
- Rate limiting setup
- Cache management
- Image validation and processing
- WebSocket utilities
- Common constants
"""
import logging
import base64
import json
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from uuid import uuid4

from fastapi import UploadFile, HTTPException

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    HAS_SLOWAPI = True
except ImportError:
    HAS_SLOWAPI = False
    logger_temp = logging.getLogger("face-attendance.common")
    logger_temp.warning("⚠️ slowapi not installed - run: pip install slowapi")
    Limiter = None
    get_remote_address = None

from backend.database.db import get_all_embeddings
from core.config import (
    SPOOF_REJECT_THRESHOLD,
    SPOOF_SUSPECT_THRESHOLD,
    SPOOF_ADAPTIVE_AREA_START_RATIO,
    SPOOF_ADAPTIVE_MAX_BONUS,
)

logger = logging.getLogger("face-attendance.common")

# ====================== RATE LIMITING ======================
if HAS_SLOWAPI:
    limiter = Limiter(key_func=get_remote_address)
    logger.info("✅ Rate limiting enabled (slowapi)")
else:
    limiter = None


# ====================== CONSTANTS ======================
DATASET_ROOT = Path("dataset")
DATASET_ROOT.mkdir(parents=True, exist_ok=True)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file size

# Registration configuration
TARGET_REGISTRATION_FRAMES = 10
MIN_ACCEPTED_REGISTRATION_FRAMES = 4
QUALITY_SCORE_THRESHOLD = 0.30

# Attendance decision thresholds
AUTO_MARK_THRESHOLD = 0.66
MANUAL_REVIEW_THRESHOLD = 0.48
SUSPECT_LIVENESS_STRONG_MATCH_DELTA = 0.04

# ====================== EMBEDDINGS CACHE ======================
embeddings_cache: List[tuple] = []


def update_embeddings_cache(rebuild_faiss: bool = True) -> None:
    """
    Reload embeddings cache from database and optionally rebuild FAISS index.
    
    Args:
        rebuild_faiss: If True, attempt to rebuild FAISS index. Disable this for 
                      fast per-registration updates.
    """
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
    """
    Fast-path: Update in-memory cache + FAISS without full reload.
    Used for incremental updates after registration.
    """
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


# ====================== IMAGE VALIDATION ======================
def validate_image_file(file: UploadFile, max_size: int = MAX_FILE_SIZE) -> bool:
    """Validate image file type and size"""
    # Check content_type if provided
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File phải là ảnh")
    
    # If content_type is not provided, check extension
    if not file.content_type:
        filename = file.filename or ""
        file_ext = filename.lower().split('.')[-1] if '.' in filename else ""
        if file_ext not in {'jpg', 'jpeg', 'png', 'bmp', 'webp', 'gif'}:
            raise HTTPException(status_code=400, detail="File phải là ảnh (jpg, png, bmp, webp, gif)")
    
    if getattr(file, 'size', None) and file.size > max_size:
        raise HTTPException(
            status_code=413, 
            detail=f"File quá lớn. Tối đa {max_size / 1024 / 1024:.0f}MB"
        )
    return True


# ====================== DATASET IMAGE HANDLING ======================
def sanitize_student_name(name: str) -> str:
    """Sanitize student name for safe filesystem usage"""
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name.strip())
    return safe.replace(" ", "_") or "student"


def save_dataset_image(student_name: str, filename: str, contents: bytes) -> str:
    """
    Save an image to the dataset directory.
    Creates student-specific subdirectory with timestamp-based naming.
    """
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


# ====================== FRAME QUALITY SCORING ======================
def score_registration_frame(frame: np.ndarray, face_image: np.ndarray, bbox: dict) -> float:
    """
    Score a registration frame based on sharpness, brightness, area ratio, 
    center position, and detection confidence.
    
    Returns a float in [0, 1] where 1.0 is highest quality.
    """
    if frame is None or face_image is None or bbox is None:
        return 0.0

    if frame.size == 0 or face_image.size == 0:
        return 0.0

    # Sharpness: Laplacian variance
    gray_face = cv2.cvtColor(face_image, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray_face, cv2.CV_64F).var())
    sharpness_score = min(1.0, sharpness / 180.0)

    # Brightness: prefer ~128 (midrange)
    brightness = float(np.mean(gray_face))
    brightness_score = max(0.0, 1.0 - abs(brightness - 128.0) / 128.0)

    # Area ratio: prefer face ~14% of frame (area_score caps at 1.0)
    frame_h, frame_w = frame.shape[:2]
    frame_area = float(frame_h * frame_w)
    face_w = float(max(0, bbox.get("w", 0)))
    face_h = float(max(0, bbox.get("h", 0)))
    face_area = face_w * face_h
    area_ratio = face_area / frame_area if frame_area > 0 else 0.0
    area_score = min(1.0, area_ratio * 7.0)

    # Center position: prefer face near center
    cx = float(bbox.get("x", 0)) + (face_w / 2.0)
    cy = float(bbox.get("y", 0)) + (face_h / 2.0)
    frame_cx = frame_w / 2.0
    frame_cy = frame_h / 2.0
    dist = float(np.hypot(cx - frame_cx, cy - frame_cy))
    max_dist = float(np.hypot(frame_cx, frame_cy))
    center_score = max(0.0, 1.0 - (dist / max_dist)) if max_dist > 0 else 0.0

    # Detection confidence
    confidence = float(bbox.get("confidence", 0.0))
    confidence_score = min(1.0, max(0.0, confidence))

    # Weighted combination
    score = (
        0.30 * sharpness_score +
        0.20 * brightness_score +
        0.20 * area_score +
        0.15 * center_score +
        0.15 * confidence_score
    )
    return float(max(0.0, min(1.0, score)))


def select_best_face_for_registration(
    faces_with_bbox: List[tuple], 
    frame_shape: tuple
) -> Optional[tuple]:
    """
    Select the best face from detection results for registration.
    Prioritizes: confidence, area ratio, and center position.
    
    Args:
        faces_with_bbox: List of (face_image, bbox) tuples from detector
        frame_shape: Shape of the frame (height, width, channels)
    
    Returns:
        (face_image, bbox) tuple or None if no suitable face found
    """
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


# ====================== WEBSOCKET UTILITIES ======================
def _decode_ws_image_to_frame(image_b64: str) -> np.ndarray:
    """
    Decode base64-encoded image from WebSocket frame to numpy array.
    Handles both data:image URIs and raw base64.
    """
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


def _model_to_dict(model) -> dict:
    """Convert Pydantic model to dictionary"""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _attach_track_ids_from_hints(results: List[dict], track_hints: List[dict]) -> List[dict]:
    """
    Attach track_id to recognition results based on spatial hints from frontend.
    Uses center-distance matching to associate results with track hints.
    """
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


__all__ = [
    # Rate limiting
    "HAS_SLOWAPI",
    "limiter",
    # Cache
    "embeddings_cache",
    "update_embeddings_cache",
    "_append_embeddings_runtime_cache",
    # Image validation
    "validate_image_file",
    # Dataset handling
    "sanitize_student_name",
    "save_dataset_image",
    # Frame quality
    "score_registration_frame",
    "select_best_face_for_registration",
    # WebSocket utilities
    "_decode_ws_image_to_frame",
    "_model_to_dict",
    "_attach_track_ids_from_hints",
    # Constants
    "DATASET_ROOT",
    "IMAGE_EXTENSIONS",
    "MAX_FILE_SIZE",
    "TARGET_REGISTRATION_FRAMES",
    "MIN_ACCEPTED_REGISTRATION_FRAMES",
    "QUALITY_SCORE_THRESHOLD",
    "AUTO_MARK_THRESHOLD",
    "MANUAL_REVIEW_THRESHOLD",
    "SUSPECT_LIVENESS_STRONG_MATCH_DELTA",
]
