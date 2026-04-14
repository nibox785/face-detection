import logging
import numpy as np
import cv2
from typing import Dict, List, Tuple

try:
    from deepface import DeepFace
except Exception:  # pragma: no cover - runtime dependency gate
    DeepFace = None

logger = logging.getLogger("face-attendance.face_engine.detect")

DETECTOR_BACKENDS = ("mtcnn", "opencv")
MIN_FACE_CONFIDENCE = 0.35


def _run_deepface_detection(image: np.ndarray, backend: str):
    return DeepFace.extract_faces(
        img_path=image,
        detector_backend=backend,
        align=True,
        enforce_detection=False,
    )

def _ensure_deepface_ready() -> None:
    if DeepFace is None:
        raise RuntimeError(
            "DeepFace chưa được cài đặt. Hãy thêm dependencies và chạy pip install -r requirements.txt"
        )

def detect_faces(frame: np.ndarray) -> List[Tuple[np.ndarray, Dict[str, float]]]:
    """
    Phát hiện khuôn mặt trong ảnh.
    
    Trả về list các tuple (cropped_face, bbox) với
    bbox = {"x": int, "y": int, "w": int, "h": int, "confidence": float}
    
    Args:
        frame: ảnh đầu vào (BGR từ OpenCV)
    
    Returns:
        list of tuples (cropped_face, bbox)
    """
    if frame is None or frame.size == 0:
        logger.warning("Input frame rỗng")
        return []

    try:
        _ensure_deepface_ready()

        # DeepFace thường ổn định hơn khi xử lý trên ảnh RGB.
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        orig_h, orig_w = frame.shape[:2]
        frame_h, frame_w = rgb_frame.shape[:2]
        scale = 1.0

        # Nếu khung hình quá nhỏ thì upscale để detector dễ bắt mặt hơn.
        if min(frame_h, frame_w) < 320:
            scale = 320.0 / float(min(frame_h, frame_w))
            rgb_frame = cv2.resize(
                rgb_frame,
                (int(frame_w * scale), int(frame_h * scale)),
                interpolation=cv2.INTER_CUBIC,
            )

        detections = []
        used_backend = "none"
        for backend in DETECTOR_BACKENDS:
            try:
                detections = _run_deepface_detection(rgb_frame, backend)
                if detections:
                    used_backend = backend
                    break
            except Exception as backend_error:
                logger.warning(
                    "DeepFace detect thất bại với backend=%s: %s",
                    backend,
                    str(backend_error),
                )

        faces: List[Tuple[np.ndarray, Dict[str, float]]] = []

        for det in detections:
            area = det.get("facial_area") or {}
            x = int(area.get("x", 0))
            y = int(area.get("y", 0))
            w = int(area.get("w", 0))
            h = int(area.get("h", 0))
            if w <= 0 or h <= 0:
                continue

            confidence = float(det.get("confidence", 0.0))
            if confidence < MIN_FACE_CONFIDENCE:
                continue

            # Quy đổi bbox từ frame đã resize về frame gốc để khung vẽ bám đúng khuôn mặt.
            x = int(round(x / scale))
            y = int(round(y / scale))
            w = int(round(w / scale))
            h = int(round(h / scale))

            x = max(0, min(x, orig_w - 1))
            y = max(0, min(y, orig_h - 1))
            w = max(1, min(w, orig_w - x))
            h = max(1, min(h, orig_h - y))

            # Loại box bất thường quá lớn thường đến từ false detection.
            area_ratio = float(w * h) / float(max(1, orig_w * orig_h))
            if area_ratio > 0.90:
                continue

            cropped_face = frame[y:y + h, x:x + w]
            if cropped_face is None or cropped_face.size == 0:
                continue

            cropped_face = cv2.resize(cropped_face, (160, 160))
            bbox = {
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "confidence": confidence,
            }
            faces.append((cropped_face, bbox))

        logger.debug("Detect faces: tim thay %d khuon mat (backend=%s)", len(faces), used_backend)
        return faces

    except Exception as e:
        logger.error(f"Lỗi khi detect faces: {str(e)}", exc_info=True)
        return []