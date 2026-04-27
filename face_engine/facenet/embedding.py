import logging
import numpy as np
import cv2
from typing import Any, Dict, Tuple

try:
    from deepface import DeepFace
except ImportError:
    DeepFace = None

logger = logging.getLogger("face-attendance.face_engine.embedding")


def _ensure_deepface():
    if DeepFace is None:
        raise RuntimeError("DeepFace chưa được cài đặt. Chạy: pip install deepface")


def _parse_liveness_result(item: Dict[str, Any]) -> Tuple[bool, float]:
    """Parse liveness fields from DeepFace output using fail-closed defaults."""
    if not isinstance(item, dict):
        return False, 1.0

    is_real = item.get("is_real")
    spoof_score = item.get("antispoof_score")

    # Backward/alternative payload shape compatibility.
    if is_real is None or spoof_score is None:
        anti_spoof = item.get("anti_spoofing")
        if isinstance(anti_spoof, dict):
            if is_real is None:
                is_real = anti_spoof.get("is_real")
            if spoof_score is None:
                spoof_score = anti_spoof.get("score")

    # DeepFace can omit anti-spoof fields in some detector flows.
    if is_real is None:
        is_real = False
    if spoof_score is None:
        spoof_score = 1.0

    try:
        spoof_score = float(spoof_score)
    except (TypeError, ValueError):
        spoof_score = 1.0

    return bool(is_real), spoof_score


def get_embedding(face_image: np.ndarray):
    """Phiên bản cũ - không có liveness"""
    if face_image is None or face_image.size == 0:
        raise ValueError("Face image rỗng")

    try:
        _ensure_deepface()

        if face_image.shape[:2] != (160, 160):
            face_image = cv2.resize(face_image, (160, 160), interpolation=cv2.INTER_AREA)

        rgb_face = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)

        embedding_obj = DeepFace.represent(
            img_path=rgb_face,
            model_name="Facenet512",
            enforce_detection=False,
            detector_backend="skip",
            align=True,
            normalization="base",
            anti_spoofing=False
        )

        embedding = np.array(embedding_obj[0]["embedding"], dtype=np.float32)
        embedding = embedding / np.linalg.norm(embedding)

        return embedding

    except Exception as e:
        logger.error(f"Lỗi extract embedding: {str(e)}", exc_info=True)
        raise


# ====================== LIVENESS DETECTION ======================
def get_embedding_with_liveness(face_image: np.ndarray):
    """
    Trích xuất embedding + kiểm tra liveness (anti-spoofing)
    Trả về: (embedding, is_real, spoof_score)
    """
    if face_image is None or face_image.size == 0:
        raise ValueError("Face image rỗng")

    try:
        _ensure_deepface()

        # Keep embedding path unchanged and stable.
        embedding = get_embedding(face_image)

        # Run anti-spoofing in detection flow (instead of represent+skip) so
        # DeepFace can return liveness fields (`is_real`, `antispoof_score`).
        liveness_result = DeepFace.extract_faces(
            img_path=face_image,
            detector_backend="opencv",
            enforce_detection=False,
            align=True,
            anti_spoofing=True,
        )

        if not liveness_result:
            logger.warning("⚠️ Liveness extract_faces không trả về khuôn mặt - reject theo fail-closed")
            return embedding, False, 1.0

        is_real, spoof_score = _parse_liveness_result(liveness_result[0])

        logger.info(f"Liveness: is_real={is_real}, spoof_score={spoof_score:.4f}")

        return embedding, bool(is_real), float(spoof_score)

    except Exception as e:
        logger.error(f"Lỗi get_embedding_with_liveness: {str(e)}", exc_info=True)
        # FAIL-CLOSED: Reject frame khi liveness check lỗi (anti-spoofing bảo vệ an niệm)
        logger.warning("⚠️ Liveness detection failed - rejecting frame for security")
        # Trả embedding dummy + is_real=False để reject
        embedding = get_embedding(face_image)
        return embedding, False, 1.0  # is_real=False để bắt buộc reject