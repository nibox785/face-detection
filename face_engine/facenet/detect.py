import logging
import numpy as np
import cv2

logger = logging.getLogger("face-attendance.face_engine.detect")

# MOCK implementation for testing without MTCNN
# In production, use: from mtcnn import MTCNN
# detector = MTCNN()

def detect_faces(frame: np.ndarray):
    """
    Phát hiện khuôn mặt trong ảnh.
    
    NOTE: This is a MOCK implementation for testing without MTCNN.
    For production, install mtcnn: pip install mtcnn
    
    Trả về list các cropped face (ảnh khuôn mặt đã cắt).
    
    Args:
        frame: ảnh đầu vào (BGR từ OpenCV)
    
    Returns:
        list of numpy arrays (cropped faces)
    """
    if frame is None or frame.size == 0:
        logger.warning("Input frame rỗng")
        return []

    try:
        # MOCK: Return a single cropped center region for testing
        # In production, use MTCNN detector.detect_faces()
        
        height, width = frame.shape[:2]
        
        # Fake: crop center area as "detected face"
        margin = 50
        x1, y1 = max(0, margin), max(0, margin)
        x2, y2 = min(width, width - margin), min(height, height - margin)
        
        if x2 - x1 > 160 and y2 - y1 > 160:
            cropped_face = frame[y1:y2, x1:x2]
            cropped_face = cv2.resize(cropped_face, (160, 160))
            logger.debug(f"MOCK Phát hiện 1 khuôn mặt")
            return [cropped_face]
        else:
            logger.warning("Frame quá nhỏ để detect")
            return []

    except Exception as e:
        logger.error(f"Lỗi khi detect faces: {str(e)}", exc_info=True)
        return []