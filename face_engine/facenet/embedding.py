import logging
import numpy as np
import cv2

try:
    from deepface import DeepFace
except Exception:  # pragma: no cover - runtime dependency gate
    DeepFace = None

logger = logging.getLogger("face-attendance.face_engine.embedding")

def _ensure_deepface_ready() -> None:
    if DeepFace is None:
        raise RuntimeError(
            "DeepFace chưa được cài đặt. Hãy thêm dependencies và chạy pip install -r requirements.txt"
        )

def get_embedding(face_image: np.ndarray):
    """
    Trích xuất embedding vector từ một khuôn mặt đã crop.
    
    Args:
        face_image: ảnh khuôn mặt đã cắt và resize (160x160, BGR)
    
    Returns:
        numpy array embedding (512 chiều)
    """
    if face_image is None or face_image.size == 0:
        logger.error("Input face_image rỗng")
        raise ValueError("Face image không hợp lệ")

    try:
        _ensure_deepface_ready()

        if face_image.shape[:2] != (160, 160):
            face_image = cv2.resize(face_image, (160, 160))

        reps = DeepFace.represent(
            img_path=face_image,
            model_name="Facenet512",
            detector_backend="skip",
            enforce_detection=False,
        )
        if not reps:
            raise ValueError("DeepFace không trả về embedding")

        embedding = np.asarray(reps[0].get("embedding"), dtype=np.float32)
        if embedding.size == 0:
            raise ValueError("Embedding rỗng")

        embedding = embedding / np.linalg.norm(embedding)
        
        logger.debug(f"Extract embedding thanh cong, shape: {embedding.shape}")
        return embedding

    except Exception as e:
        logger.error(f"Lỗi khi extract embedding: {str(e)}", exc_info=True)
        raise