import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from face_engine.facenet.detect import _safe_bbox


def test_safe_bbox_clamps_negative_values():
    bbox = _safe_bbox({"x": -10, "y": -5, "w": 100, "h": 80}, (480, 640, 3))

    assert bbox == {"x": 0, "y": 0, "w": 100, "h": 80}


def test_safe_bbox_limits_to_frame_size():
    bbox = _safe_bbox({"x": 620, "y": 470, "w": 50, "h": 30}, (480, 640, 3))

    assert bbox == {"x": 620, "y": 470, "w": 20, "h": 10}


def test_safe_bbox_uses_x2_y2_when_width_height_missing():
    bbox = _safe_bbox({"x": 20, "y": 30, "x2": 120, "y2": 150}, (480, 640, 3))

    assert bbox == {"x": 20, "y": 30, "w": 100, "h": 120}