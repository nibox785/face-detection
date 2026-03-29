import logging
import numpy as np
from deepface import DeepFace
import cv2

logger = logging.getLogger("face-attendance.face_engine.embedding")

# Sử dụng DeepFace với model FaceNet (rất tiện và ổn định)
# Model name: "Facenet" hoặc "Facenet512"

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
        # Chuyển BGR sang RGB (DeepFace yêu cầu)
        rgb_face = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)

        # Sử dụng DeepFace để lấy embedding
        embedding_obj = DeepFace.represent(
            img_path=rgb_face,           # truyền trực tiếp array
            model_name="Facenet512",     # hoặc "Facenet" nếu muốn 128 chiều
            enforce_detection=False,     # vì đã crop rồi
            detector_backend="skip",     # bỏ qua detect vì đã có face
            align=True,
            normalization="base"
        )

        embedding = np.array(embedding_obj[0]["embedding"])
        
        # Normalize L2 (chuẩn FaceNet)
        embedding = embedding / np.linalg.norm(embedding)
        
        logger.debug(f"Extract embedding thành công, shape: {embedding.shape}")
        return embedding

    except Exception as e:
        logger.error(f"Lỗi khi extract embedding: {str(e)}", exc_info=True)
        raise