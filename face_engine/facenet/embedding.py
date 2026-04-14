import logging
import numpy as np
import cv2

try:
    from deepface import DeepFace
except ImportError:
    DeepFace = None

logger = logging.getLogger("face-attendance.face_engine.embedding")


def _ensure_deepface():
    if DeepFace is None:
        raise RuntimeError("DeepFace chưa được cài đặt. Chạy: pip install deepface")


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


# ====================== HÀM MỚI: LIVENESS DETECTION ======================
def get_embedding_with_liveness(face_image: np.ndarray):
    """
    Trích xuất embedding + kiểm tra liveness (anti-spoofing)
    Trả về: (embedding, is_real, spoof_score)
    """
    if face_image is None or face_image.size == 0:
        raise ValueError("Face image rỗng")

    try:
        _ensure_deepface()

        if face_image.shape[:2] != (160, 160):
            face_image = cv2.resize(face_image, (160, 160), interpolation=cv2.INTER_AREA)

        rgb_face = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)

        # Bật anti_spoofing
        result = DeepFace.represent(
            img_path=rgb_face,
            model_name="Facenet512",
            enforce_detection=False,
            detector_backend="skip",
            align=True,
            normalization="base",
            anti_spoofing=True          # ← Quan trọng
        )

        embedding = np.array(result[0]["embedding"], dtype=np.float32)
        embedding = embedding / np.linalg.norm(embedding)

        # Lấy kết quả liveness
        anti_spoof = result[0].get("anti_spoofing", {})
        is_real = anti_spoof.get("is_real", True)
        spoof_score = anti_spoof.get("score", 0.0)   # Score càng cao càng nghi ngờ giả mạo

        logger.info(f"Liveness: is_real={is_real}, spoof_score={spoof_score:.4f}")

        return embedding, bool(is_real), float(spoof_score)

    except Exception as e:
        logger.error(f"Lỗi get_embedding_with_liveness: {str(e)}", exc_info=True)
        # Fallback nếu anti_spoofing lỗi
        embedding = get_embedding(face_image)
        return embedding, True, 0.0