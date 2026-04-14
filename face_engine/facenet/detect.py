import logging
from typing import Dict, List, Tuple

import numpy as np

try:
    from deepface import DeepFace
except ImportError:
    DeepFace = None

logger = logging.getLogger("face-attendance.face_engine.detect")


def _ensure_deepface() -> None:
    if DeepFace is None:
        raise RuntimeError("DeepFace chưa được cài đặt. Chạy: pip install deepface")


def _safe_bbox(area: Dict, frame_shape: Tuple[int, int, int]) -> Dict:
    h_frame, w_frame = frame_shape[:2]

    x = int(max(0, area.get("x", 0)))
    y = int(max(0, area.get("y", 0)))
    w = int(max(0, area.get("w", 0)))
    h = int(max(0, area.get("h", 0)))

    if w <= 0 and "x2" in area:
        w = int(max(0, int(area.get("x2", x)) - x))
    if h <= 0 and "y2" in area:
        h = int(max(0, int(area.get("y2", y)) - y))

    if x + w > w_frame:
        w = max(0, w_frame - x)
    if y + h > h_frame:
        h = max(0, h_frame - y)

    return {"x": x, "y": y, "w": w, "h": h}


def detect_faces(frame: np.ndarray) -> List[Tuple[np.ndarray, Dict]]:
    """Trả về danh sách (face_image, bbox) với bbox gồm x, y, w, h, confidence."""
    if frame is None or frame.size == 0:
        return []

    try:
        _ensure_deepface()

        detected = DeepFace.extract_faces(
            img_path=frame,
            detector_backend="retinaface",
            enforce_detection=False,
            align=True,
            anti_spoofing=False,
        )

        results: List[Tuple[np.ndarray, Dict]] = []
        for item in detected:
            area = item.get("facial_area", {}) if isinstance(item, dict) else {}
            bbox = _safe_bbox(area, frame.shape)

            x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
            if w <= 0 or h <= 0:
                continue

            face_image = frame[y : y + h, x : x + w].copy()
            if face_image.size == 0:
                continue

            bbox["confidence"] = float(item.get("confidence", 0.0)) if isinstance(item, dict) else 0.0
            results.append((face_image, bbox))

        results.sort(key=lambda item: float(item[1].get("confidence", 0.0)), reverse=True)
        return results

    except Exception as e:
        logger.error(f"Lỗi detect_faces: {str(e)}", exc_info=True)
        return []