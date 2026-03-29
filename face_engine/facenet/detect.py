import logging
import numpy as np
from mtcnn import MTCNN
import cv2

logger = logging.getLogger("face-attendance.face_engine.detect")

# Khởi tạo detector một lần (singleton style)
detector = MTCNN()

def detect_faces(frame: np.ndarray):
    """
    Phát hiện khuôn mặt trong ảnh.
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
        # Chuyển sang RGB vì MTCNN yêu cầu RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        detections = detector.detect_faces(rgb_frame)
        logger.debug(f"Phát hiện {len(detections)} khuôn mặt")

        faces = []
        for i, det in enumerate(detections):
            x, y, width, height = det['box']
            confidence = det['confidence']

            # Lọc confidence thấp
            if confidence < 0.9:
                logger.debug(f"Khuôn mặt {i} có confidence thấp ({confidence:.2f}), bỏ qua")
                continue

            # Cắt khuôn mặt + thêm margin nhỏ để embedding tốt hơn
            x1 = max(0, x - 10)
            y1 = max(0, y - 10)
            x2 = min(frame.shape[1], x + width + 10)
            y2 = min(frame.shape[0], y + height + 10)

            cropped_face = frame[y1:y2, x1:x2]
            
            # Resize về kích thước chuẩn cho FaceNet (160x160)
            cropped_face = cv2.resize(cropped_face, (160, 160))
            faces.append(cropped_face)

        return faces

    except Exception as e:
        logger.error(f"Lỗi khi detect faces: {str(e)}", exc_info=True)
        return []