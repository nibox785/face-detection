import logging
import numpy as np

logger = logging.getLogger("face-attendance.face_engine.embedding")

def get_embedding(face_image: np.ndarray):
    """
    Trích xuất embedding vector từ một khuôn mặt đã crop.
    
    NOTE: This is a MOCK implementation for testing without deepface.
    For production, install deepface: pip install deepface
    
    Args:
        face_image: ảnh khuôn mặt đã cắt và resize (160x160, BGR)
    
    Returns:
        numpy array embedding (512 chiều fake data)
    """
    if face_image is None or face_image.size == 0:
        logger.error("Input face_image rỗng")
        raise ValueError("Face image không hợp lệ")

    try:
        # MOCK: Generate random embedding for testing
        # In production, use DeepFace.represent() instead
        embedding = np.random.randn(512).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)
        
        logger.debug(f"Extract embedding thành công (MOCK), shape: {embedding.shape}")
        return embedding

    except Exception as e:
        logger.error(f"Lỗi khi extract embedding: {str(e)}", exc_info=True)
        raise