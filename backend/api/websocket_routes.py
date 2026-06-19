"""
WebSocket routes: /ws/recognize, /ws/realtime/{session_id}
Real-time face recognition with streaming support
"""
import logging
import json
import time
from typing import List, Optional, Dict
from uuid import uuid4

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosedOK

from backend.services.face_service import FaceService
from backend.services.attendance_service import AttendanceService
from backend.database.db import get_student_by_id
from backend.database.schemas import RecognizeResult
from core.config import (
    REALTIME_WS_DETECT_INTERVAL_MS,
    REALTIME_WS_TRACK_TTL_MS,
    REALTIME_WS_RECOGNIZE_COOLDOWN_MS,
)
from .auth_routes import verify_access_token
from .common import (
    _decode_ws_image_to_frame,
    _model_to_dict,
    _attach_track_ids_from_hints,
    embeddings_cache,
)
from .recognize_routes import (
    run_recognition_on_frame,
    run_recognition_on_face_crop,
)

logger = logging.getLogger("face-attendance.websocket_routes")

websocket_router = APIRouter(prefix="", tags=["websocket"])

# ====================== SERVICES ======================
face_service = FaceService(threshold=0.68)
attendance_service = AttendanceService()

# session_id -> {"tracks": List[dict], "last_seen_ms": int, "attended_student_ids": set}
_realtime_sessions: dict[str, dict] = {}


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _center_of_bbox(bbox: dict) -> tuple[float, float]:
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    w = float(bbox.get("w", 0))
    h = float(bbox.get("h", 0))
    return (x + w / 2.0, y + h / 2.0)


def _match_detections_to_tracks(
    detections: List[dict],
    tracks: List[dict],
    max_center_dist_px: float = 160.0,
) -> tuple[dict[int, int], set[int], set[int]]:
    """
    Greedy center-distance assignment.
    Returns:
      - det_to_track: det_idx -> track_idx
      - used_det_idxs
      - used_track_idxs
    """
    det_centers = [_center_of_bbox(det["bbox"]) for det in detections]
    track_centers = [_center_of_bbox(tr["bbox"]) for tr in tracks]

    pairs = []
    for di, (dcx, dcy) in enumerate(det_centers):
        for ti, (tcx, tcy) in enumerate(track_centers):
            dist = float(np.hypot(dcx - tcx, dcy - tcy))
            if dist <= max_center_dist_px:
                pairs.append((dist, di, ti))
    pairs.sort(key=lambda item: item[0])

    det_to_track: dict[int, int] = {}
    used_det = set()
    used_track = set()
    for dist, di, ti in pairs:
        if di in used_det or ti in used_track:
            continue
        det_to_track[di] = ti
        used_det.add(di)
        used_track.add(ti)

    return det_to_track, used_det, used_track


def _create_cv2_tracker():
    """
    Prefer very fast trackers for realtime bbox continuity.
    MOSSE is typically the fastest; fallback to KCF.
    """
    # OpenCV 4.x may expose trackers under cv2.legacy
    legacy = getattr(cv2, "legacy", None)
    if legacy is not None:
        if hasattr(legacy, "TrackerMOSSE_create"):
            return legacy.TrackerMOSSE_create()
        if hasattr(legacy, "TrackerKCF_create"):
            return legacy.TrackerKCF_create()

    if hasattr(cv2, "TrackerMOSSE_create"):
        return cv2.TrackerMOSSE_create()
    if hasattr(cv2, "TrackerKCF_create"):
        return cv2.TrackerKCF_create()

    return None


@websocket_router.websocket("/ws/recognize")
async def recognize_stream(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    try:
        verify_access_token(token)
    except Exception:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    logger.info("WS recognize connected")

    try:
        while True:
            raw_message = await websocket.receive_text()
            payload = json.loads(raw_message)
            msg_type = payload.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": int(time.time() * 1000)})
                continue

            if msg_type != "frame":
                await websocket.send_json({"type": "error", "message": "Unsupported message type"})
                continue

            frame_id = payload.get("frame_id")
            image_b64 = payload.get("image")
            track_hints = payload.get("track_hints") or []

            try:
                frame = _decode_ws_image_to_frame(image_b64)
                results = run_recognition_on_frame(frame)
                result_dicts = [_model_to_dict(item) for item in results]
                result_dicts = _attach_track_ids_from_hints(result_dicts, track_hints)

                await websocket.send_json({
                    "type": "recognize_result",
                    "frame_id": frame_id,
                    "results": result_dicts,
                })
            except Exception as e:
                logger.error(f"WS recognize frame error: {str(e)}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "frame_id": frame_id,
                    "message": str(e),
                })
    except WebSocketDisconnect:
        logger.info("WS recognize disconnected")
    except Exception as e:
        logger.error(f"WS recognize fatal error: {str(e)}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass


@websocket_router.websocket("/ws/realtime/{session_id}")
async def realtime_track_stream(websocket: WebSocket, session_id: str):
    """
    Realtime WS theo session (Mode B: backend detect + track):
    - FE gửi full frame (JPEG base64)
    - Backend detect + assign track_id + (throttle) recognize theo track
    - Backend trả về tracks với bbox + result để FE vẽ overlay liên tục
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    try:
        verify_access_token(token)
    except Exception:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    logger.info(f"WS realtime connected session_id={session_id}")

    # Init / attach session tracker state
    session = _realtime_sessions.get(session_id)
    if not session:
        session = {
            "tracks": [],
            "last_seen_ms": _now_ms(),
            "last_detect_ms": 0,
            "attended_student_ids": set(),
        }
        _realtime_sessions[session_id] = session
    tracks: List[dict] = session["tracks"]
    attended_student_ids: set = session.get("attended_student_ids") or set()
    session["attended_student_ids"] = attended_student_ids

    try:
        while True:
            raw_message = await websocket.receive_text()
            payload = json.loads(raw_message)
            msg_type = payload.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": int(time.time() * 1000)})
                continue

            if msg_type != "frame":
                await websocket.send_json({"type": "error", "message": "Unsupported message type"})
                continue
            frame_id = payload.get("frame_id")
            image_b64 = payload.get("image")

            try:
                now_ms = _now_ms()
                session["last_seen_ms"] = now_ms

                frame = _decode_ws_image_to_frame(image_b64)

                # 1) Update trackers every WS frame to keep bbox smooth.
                for tr in tracks:
                    tracker = tr.get("tracker")
                    if tracker is None:
                        continue
                    try:
                        ok, box = tracker.update(frame)
                        if ok and box is not None:
                            x, y, w, h = box
                            tr["bbox"] = {
                                "x": float(x),
                                "y": float(y),
                                "w": float(w),
                                "h": float(h),
                                "confidence": float(tr.get("bbox", {}).get("confidence", 0.0) if tr.get("bbox") else 0.0),
                            }
                            tr["last_seen_ms"] = now_ms
                    except Exception:
                        pass

                # 2) Run heavy face detection at a lower rate
                detect_interval_ms = max(120, int(REALTIME_WS_DETECT_INTERVAL_MS))
                should_detect = (now_ms - int(session.get("last_detect_ms", 0))) >= detect_interval_ms

                detections: List[dict] = []
                if should_detect:
                    session["last_detect_ms"] = now_ms
                    faces_with_bbox = face_service.detect(frame)
                    for face_img, bbox in faces_with_bbox:
                        detections.append({
                            "face": face_img,
                            "bbox": {
                                "x": bbox.get("x", 0),
                                "y": bbox.get("y", 0),
                                "w": bbox.get("w", 0),
                                "h": bbox.get("h", 0),
                                "confidence": float(bbox.get("confidence", 0.0)),
                            } if bbox else None,
                        })

                # Drop stale tracks
                track_ttl_ms = max(600, int(REALTIME_WS_TRACK_TTL_MS))
                tracks[:] = [
                    tr for tr in tracks
                    if now_ms - int(tr.get("last_seen_ms", now_ms)) <= track_ttl_ms
                ]

                if detections:
                    # Match detections to existing tracks
                    det_to_track, used_det, used_track = _match_detections_to_tracks(detections, tracks)

                    # Update matched tracks (and refresh trackers)
                    for det_idx, tr_idx in det_to_track.items():
                        det = detections[det_idx]
                        tr = tracks[tr_idx]
                        tr["bbox"] = det["bbox"]
                        tr["last_seen_ms"] = now_ms
                        tr["seen_count"] = int(tr.get("seen_count", 0)) + 1
                        tr["face"] = det["face"]

                        tracker = _create_cv2_tracker()
                        if tracker is not None and det.get("bbox"):
                            try:
                                b = det["bbox"]
                                tracker.init(frame, (float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])))
                                tr["tracker"] = tracker
                            except Exception:
                                tr["tracker"] = None

                    # Create new tracks for unmatched detections
                    for det_idx, det in enumerate(detections):
                        if det_idx in used_det:
                            continue
                        tracker = _create_cv2_tracker()
                        if tracker is not None and det.get("bbox"):
                            try:
                                b = det["bbox"]
                                tracker.init(frame, (float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])))
                            except Exception:
                                tracker = None
                        tracks.append({
                            "track_id": f"trk-{uuid4().hex[:10]}",
                            "bbox": det["bbox"],
                            "last_seen_ms": now_ms,
                            "seen_count": 1,
                            "last_recognized_ms": 0,
                            "result": None,
                            "face": det["face"],
                            "tracker": tracker,
                        })

                # Recognition throttle per track
                recognize_cooldown_ms = max(250, int(REALTIME_WS_RECOGNIZE_COOLDOWN_MS))
                outbound_tracks = []
                for tr in tracks:
                    face_img = tr.get("face")
                    per_track_cooldown_ms = int(tr.get("recognize_cooldown_ms", 0) or 0)
                    effective_cooldown_ms = max(recognize_cooldown_ms, per_track_cooldown_ms)
                    should_recognize = (
                        face_img is not None
                        and now_ms - int(tr.get("last_recognized_ms", 0)) >= effective_cooldown_ms
                    )

                    if should_recognize:
                        result_model = run_recognition_on_face_crop(face_img)
                        tr["last_recognized_ms"] = now_ms
                        result_dict = _model_to_dict(result_model) if result_model else None

                        # If this student was already marked in this session,
                        # annotate the result and increase cooldown.
                        if isinstance(result_dict, dict) and result_dict.get("student_id"):
                            sid = result_dict.get("student_id")
                            if sid in attended_student_ids:
                                result_dict["attendance_status"] = "ALREADY_MARKED"
                                tr["recognize_cooldown_ms"] = max(int(tr.get("recognize_cooldown_ms", 0) or 0), 3000)
                            else:
                                # Mark attendance once per session for this student.
                                try:
                                    marked = attendance_service.mark_attendance(sid)
                                except Exception:
                                    marked = False
                                attended_student_ids.add(sid)
                                result_dict["attendance_status"] = "MARKED" if marked else "ALREADY_MARKED"
                                tr["recognize_cooldown_ms"] = max(int(tr.get("recognize_cooldown_ms", 0) or 0), 2500)

                        tr["result"] = result_dict

                    # Do not keep raw face in memory across ticks
                    tr["face"] = None

                    outbound_tracks.append({
                        "track_id": tr.get("track_id"),
                        "bbox": tr.get("bbox"),
                        "result": tr.get("result"),
                        "last_seen_ms": tr.get("last_seen_ms"),
                    })

                await websocket.send_json({
                    "type": "frame_result",
                    "session_id": session_id,
                    "frame_id": frame_id,
                    "tracks": outbound_tracks,
                })
            except Exception as e:
                logger.error(f"WS realtime frame error: {str(e)}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "session_id": session_id,
                    "frame_id": frame_id,
                    "message": str(e),
                })
    except WebSocketDisconnect:
        logger.info(f"WS realtime disconnected session_id={session_id}")
    except Exception as e:
        logger.error(f"WS realtime fatal error session_id={session_id}: {str(e)}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass
    finally:
        # Best-effort cleanup
        try:
            session = _realtime_sessions.get(session_id)
            if session:
                session["tracks"] = []
                session["last_seen_ms"] = _now_ms()
                session["attended_student_ids"] = set()
        except Exception:
            pass
