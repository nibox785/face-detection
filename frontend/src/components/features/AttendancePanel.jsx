import { useEffect, useRef, useState, useCallback } from 'react';
import { apiFetch, buildRealtimeWsUrl } from '../../api/apiClient';
import * as XLSX from 'xlsx';  
import ConfirmDialog from '../common/ConfirmDialog';

const RECOGNITION_INTERVAL_MS = 250;
// Server-side tracking can be slower than draw loop; keep tracks longer to avoid flicker.
const TRACK_RETENTION_MS = 1600;
const TRACK_PREDICTION_MAX_MS = 460;
const TRACK_MATCH_DISTANCE_PX = 140;
const VELOCITY_DAMPING = 0.91;

const MAX_LATENCY_SAMPLES = 40;
const MOTION_SAMPLE_WIDTH = 96;
const MOTION_SAMPLE_HEIGHT = 54;
const MOTION_PIXEL_DELTA_THRESHOLD = 14;
const MOTION_ACTIVE_RATIO_THRESHOLD = 0.08;
const FORCE_SEND_INTERVAL_MS = 2200;
const ATTENDANCE_LOG_THRESHOLD = 0.66;
const LOCAL_DETECT_INTERVAL_MS = 85;
const RECOGNITION_TO_TRACK_MATCH_PX = TRACK_MATCH_DISTANCE_PX * 1.8;
// Keep this low to avoid backlog (stale results arriving in bursts).
const WS_MAX_PENDING_FRAMES = 1;
const WS_SEND_MAX_WIDTH = 416;
const WS_SEND_JPEG_QUALITY_MIN = 0.55;
const WS_SEND_JPEG_QUALITY_MAX = 0.82;

const ATTENDANCE_SESSION_RUNNING_KEY = 'fa_attendance_session_running';

function AttendancePanel() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const drawCanvasRef = useRef(null);
  const isProcessingRef = useRef(false);
  const lastRunAtRef = useRef(0);
  const toastTimerRef = useRef(null);
  const rafIdRef = useRef(null);
  const trackedFacesRef = useRef([]);
  const lastDrawTsRef = useRef(0);
  const fpsFrameCountRef = useRef(0);
  const apiCallTimestampsRef = useRef([]);
  const latencySamplesRef = useRef([]);
  const telemetryTimelineRef = useRef([]);
  // Decision totals for telemetry are tracked per-student (unique within session),
  // not per-frame, to avoid inflating counts when the same student stays in view.
  const decisionCountersRef = useRef({ AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 });
  const decisionSetsRef = useRef({
    AUTO_MARK: new Set(),
    MANUAL_REVIEW: new Set(),
    REJECT: new Set(),
  });
  // Additional research counters: per-frame (each result counts, can be higher than unique).
  const frameDecisionCountersRef = useRef({ AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 });
  const recognitionEventsRef = useRef([]);
  const sessionStartedAtRef = useRef(null);
  const motionCanvasRef = useRef(null);
  const prevMotionSampleRef = useRef(null);
  const lastApiSentAtRef = useRef(0);
  const lastDetectedAtRef = useRef(0);
  const faceDetectorRef = useRef(null);
  const hasLocalDetectorRef = useRef(false);
  const isLocalDetectingRef = useRef(false);
  const lastLocalDetectAtRef = useRef(0);
  const wsRef = useRef(null);
  const pendingWsFramesRef = useRef(new Map());
  const wsBackoffTimerRef = useRef(null);
  const sessionIdRef = useRef(null);
  const lastWsAppliedSentAtRef = useRef(0);
  const exportedAttendanceExcelRef = useRef(false);

  const [isRunning, setIsRunning] = useState(false);
  const [log, setLog] = useState([]);
  const [stream, setStream] = useState(null);
  const [expectedStudents, setExpectedStudents] = useState([]); // từ file Excel import
  const [sessionAttendance, setSessionAttendance] = useState(new Map()); // student_id -> {mssv, name, status}
  const [toast, setToast] = useState(null);
  const [latestResults, setLatestResults] = useState([]);
  const [telemetry, setTelemetry] = useState({
    fps: 0,
    apiCallsPerMin: 0,
    lastLatencyMs: 0,
    avgLatencyMs: 0,
  });
  const [decisionStats, setDecisionStats] = useState({ AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 });
  const [frameDecisionStats, setFrameDecisionStats] = useState({ AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 });
  const [wsConnected, setWsConnected] = useState(false);
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false);

  const attendedSet = useRef(new Set()); // Ngăn ghi log lặp lại trong cùng phiên
  const bestDecisionByStudentRef = useRef(new Map()); // student_id -> best decision observed in this session

  function decisionRank(decision) {
    const value = String(decision || 'REJECT');
    if (value === 'AUTO_MARK') return 3;
    if (value === 'MANUAL_REVIEW') return 2;
    return 1; // REJECT / unknown
  }

  function normalizePersonKey(value) {
    return String(value || '')
      .trim()
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/đ/g, 'd')
      .replace(/\s+/g, ' ');
  }

  function formatTimeHms(dateLike) {
    const d = dateLike instanceof Date ? dateLike : new Date(dateLike);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('vi-VN', { hour12: false });
  }

  function formatSinceStartMs(diffMs) {
    const safe = Math.max(0, Number(diffMs || 0));
    const totalSeconds = Math.floor(safe / 1000);
    const hh = Math.floor(totalSeconds / 3600);
    const mm = Math.floor((totalSeconds % 3600) / 60);
    const ss = totalSeconds % 60;
    const mmStr = String(mm).padStart(2, '0');
    const ssStr = String(ss).padStart(2, '0');
    if (hh > 0) {
      return `${String(hh).padStart(2, '0')}:${mmStr}'${ssStr}s`;
    }
    return `${mmStr}'${ssStr}s`;
  }

  function recomputeUniqueDecisionCounters() {
    decisionCountersRef.current = {
      AUTO_MARK: decisionSetsRef.current.AUTO_MARK.size,
      MANUAL_REVIEW: decisionSetsRef.current.MANUAL_REVIEW.size,
      REJECT: decisionSetsRef.current.REJECT.size,
    };
  }

  function applyUniqueDecision(studentId, decision) {
    if (!studentId) return;
    const sid = String(studentId);
    const next = String(decision || 'REJECT');

    // Enforce monotonic upgrade: AUTO_MARK > MANUAL_REVIEW > REJECT.
    // If a student reaches AUTO_MARK, remove them from other buckets.
    if (next === 'AUTO_MARK') {
      decisionSetsRef.current.AUTO_MARK.add(sid);
      decisionSetsRef.current.MANUAL_REVIEW.delete(sid);
      decisionSetsRef.current.REJECT.delete(sid);
      return;
    }
    if (next === 'MANUAL_REVIEW') {
      if (!decisionSetsRef.current.AUTO_MARK.has(sid)) {
        decisionSetsRef.current.MANUAL_REVIEW.add(sid);
        decisionSetsRef.current.REJECT.delete(sid);
      }
      return;
    }
    // REJECT
    if (!decisionSetsRef.current.AUTO_MARK.has(sid) && !decisionSetsRef.current.MANUAL_REVIEW.has(sid)) {
      decisionSetsRef.current.REJECT.add(sid);
    }
  }

  // Keep a single source of truth for "session running" across tabs.
  useEffect(() => {
    try {
      sessionStorage.setItem(ATTENDANCE_SESSION_RUNNING_KEY, isRunning ? '1' : '0');
    } catch (_) {
      // ignore
    }
    return () => {
      // Component unmount safeguard
      try {
        sessionStorage.setItem(ATTENDANCE_SESSION_RUNNING_KEY, '0');
      } catch (_) {
        // ignore
      }
    };
  }, [isRunning]);

  // Cleanup camera + WS resources
  useEffect(() => {
    return () => {
      if (stream) stream.getTracks().forEach(track => track.stop());
      if (toastTimerRef.current) {
        clearTimeout(toastTimerRef.current);
      }
      if (wsBackoffTimerRef.current) {
        clearTimeout(wsBackoffTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [stream]);

  // ==================== 1. BẮT ĐẦU CAMERA + REAL-TIME 30FPS ====================
  async function startCamera() {
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } }
      });
      videoRef.current.srcObject = media;
      await videoRef.current.play();
      setStream(media);
      return media;
    } catch (err) {
      console.error(err);
      alert("Không thể mở camera. Vui lòng kiểm tra quyền truy cập.");
      return null;
    }
  }

  const getAdaptiveJpegQuality = useCallback(() => {
    const avgLatency = Number(telemetry.avgLatencyMs || 0);
    const pending = pendingWsFramesRef.current.size;
    if (avgLatency >= 1500 || pending >= 2) return WS_SEND_JPEG_QUALITY_MIN;
    if (avgLatency >= 900 || pending >= 1) return 0.62;
    if (avgLatency >= 600) return 0.7;
    return WS_SEND_JPEG_QUALITY_MAX;
  }, [telemetry.avgLatencyMs]);

  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return null;

    const sourceWidth = video.videoWidth || 640;
    const sourceHeight = video.videoHeight || 480;
    const scale = Math.min(1, WS_SEND_MAX_WIDTH / Math.max(1, sourceWidth));
    const width = Math.max(1, Math.round(sourceWidth * scale));
    const height = Math.max(1, Math.round(sourceHeight * scale));

    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise(resolve => {
      canvas.toBlob(blob => resolve(blob), 'image/jpeg', getAdaptiveJpegQuality());
    });
  }, [getAdaptiveJpegQuality]);

  const blobToDataUrl = useCallback((blob) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('Không thể chuyển ảnh sang base64'));
      reader.readAsDataURL(blob);
    });
  }, []);

  const collectTrackHints = useCallback(() => {
    return (trackedFacesRef.current || [])
      .filter((track) => Number.isFinite(track.x) && Number.isFinite(track.y))
      .map((track) => ({
        track_id: track.id,
        x: Math.round(track.x),
        y: Math.round(track.y),
        w: Math.round(track.w),
        h: Math.round(track.h),
      }));
  }, []);

  const initLocalDetector = useCallback(() => {
    if (hasLocalDetectorRef.current) return;

    try {
      if (typeof window !== 'undefined' && 'FaceDetector' in window) {
        faceDetectorRef.current = new window.FaceDetector({
          fastMode: true,
          maxDetectedFaces: 5,
        });
        hasLocalDetectorRef.current = true;
      }
    } catch (error) {
      console.warn('Local FaceDetector init failed, fallback to backend bboxes:', error);
      faceDetectorRef.current = null;
      hasLocalDetectorRef.current = false;
    }
  }, []);

  const measureMotion = useCallback(() => {
    const video = videoRef.current;
    if (!video) {
      return { isMotion: true, activeRatio: 1 };
    }

    if (!motionCanvasRef.current) {
      motionCanvasRef.current = document.createElement('canvas');
      motionCanvasRef.current.width = MOTION_SAMPLE_WIDTH;
      motionCanvasRef.current.height = MOTION_SAMPLE_HEIGHT;
    }

    const motionCanvas = motionCanvasRef.current;
    const motionCtx = motionCanvas.getContext('2d', { willReadFrequently: true });
    motionCtx.drawImage(video, 0, 0, MOTION_SAMPLE_WIDTH, MOTION_SAMPLE_HEIGHT);

    const frame = motionCtx.getImageData(0, 0, MOTION_SAMPLE_WIDTH, MOTION_SAMPLE_HEIGHT).data;
    const prev = prevMotionSampleRef.current;
    prevMotionSampleRef.current = frame;

    if (!prev || prev.length !== frame.length) {
      return { isMotion: true, activeRatio: 1 };
    }

    let activePixels = 0;
    const pixelCount = MOTION_SAMPLE_WIDTH * MOTION_SAMPLE_HEIGHT;

    for (let i = 0; i < frame.length; i += 4) {
      const currGray = (frame[i] + frame[i + 1] + frame[i + 2]) / 3;
      const prevGray = (prev[i] + prev[i + 1] + prev[i + 2]) / 3;
      if (Math.abs(currGray - prevGray) >= MOTION_PIXEL_DELTA_THRESHOLD) {
        activePixels += 1;
      }
    }

    const activeRatio = activePixels / pixelCount;
    return {
      isMotion: activeRatio >= MOTION_ACTIVE_RATIO_THRESHOLD,
      activeRatio,
    };
  }, []);

  // ==================== 2 & 4. XỬ LÝ ĐIỂM DANH + CHỈ GHI 1 LẦN ====================
  const showAttendanceToast = useCallback((studentName) => {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }

    setToast({
      id: `${Date.now()}-${studentName}`,
      message: `Đã điểm danh thành công: ${studentName}`
    });

    toastTimerRef.current = setTimeout(() => {
      setToast(null);
    }, 2200);
  }, []);

  function centerOf(box) {
    return {
      cx: box.x + box.w / 2,
      cy: box.y + box.h / 2,
    };
  }

  function mergeTrackedFaces(detections, options = {}) {
    const {
      defaultColor = '#ffaa00',
      defaultLabel = 'Detecting...',
    } = options;

    const now = Date.now();
    if (!Array.isArray(detections)) return;

    const previous = trackedFacesRef.current || [];
    const usedIndexes = new Set();
    const next = [];

    detections.forEach((det) => {
      const detCenter = centerOf(det);
      let bestIndex = -1;
      let bestDistance = Number.POSITIVE_INFINITY;

      previous.forEach((track, idx) => {
        if (usedIndexes.has(idx)) return;

        const trackCenter = centerOf(track);
        const dist = Math.hypot(detCenter.cx - trackCenter.cx, detCenter.cy - trackCenter.cy);
        if (dist < bestDistance) {
          bestDistance = dist;
          bestIndex = idx;
        }
      });

      if (bestIndex >= 0 && bestDistance <= TRACK_MATCH_DISTANCE_PX) {
        const prevTrack = previous[bestIndex];
        usedIndexes.add(bestIndex);

        const dt = Math.max(16, now - (prevTrack.lastSeenAt || now));
        const vx = ((det.x - prevTrack.x) / dt) * 1000;
        const vy = ((det.y - prevTrack.y) / dt) * 1000;

        next.push({
          ...prevTrack,
          ...det,
          label: det.label ?? prevTrack.label ?? defaultLabel,
          color: det.color ?? prevTrack.color ?? defaultColor,
          studentId: det.studentId ?? prevTrack.studentId ?? null,
          score: Number(det.score ?? prevTrack.score ?? 0),
          vx,
          vy,
          lastSeenAt: now,
        });
      } else {
        next.push({
          id: `track-${now}-${Math.random().toString(16).slice(2, 8)}`,
          ...det,
          label: det.label ?? defaultLabel,
          color: det.color ?? defaultColor,
          studentId: det.studentId ?? null,
          score: Number(det.score ?? 0),
          vx: 0,
          vy: 0,
          lastSeenAt: now,
        });
      }
    });

    const carryForward = previous
      .filter((_, idx) => !usedIndexes.has(idx))
      .filter((track) => now - (track.lastSeenAt || now) <= TRACK_RETENTION_MS)
      .map((track) => ({
        ...track,
        vx: track.vx * VELOCITY_DAMPING,
        vy: track.vy * VELOCITY_DAMPING,
      }));

    trackedFacesRef.current = [...next, ...carryForward];
  }

  function updateTrackedFacesFromResults(results) {
    const detections = (results || [])
      .filter(result => result?.bbox)
      .map((result) => {
        const { x = 0, y = 0, w = 0, h = 0 } = result.bbox || {};
        return {
          x,
          y,
          w,
          h,
          score: Number(result.score || 0),
          studentId: result.student_id ?? null,
          label: result.name || 'Unknown',
          color: result.student_id ? '#00ff00' : '#ffaa00',
        };
      });

    mergeTrackedFaces(detections, {
      defaultColor: '#ffaa00',
      defaultLabel: 'Unknown',
    });
  }

  function applyRecognitionToLocalTracks(results) {
    const tracks = trackedFacesRef.current || [];
    if (!tracks.length) {
      updateTrackedFacesFromResults(results);
      return;
    }

    const usedTrackIndexes = new Set();
    const now = Date.now();

    (results || []).forEach((result) => {
      if (!result?.bbox) return;

      const { x = 0, y = 0, w = 0, h = 0 } = result.bbox;
      const rcx = x + w / 2;
      const rcy = y + h / 2;
      let bestIdx = -1;
      let bestDist = Number.POSITIVE_INFINITY;

      tracks.forEach((track, idx) => {
        if (usedTrackIndexes.has(idx)) return;
        const tcx = track.x + track.w / 2;
        const tcy = track.y + track.h / 2;
        const dist = Math.hypot(rcx - tcx, rcy - tcy);
        if (dist < bestDist) {
          bestDist = dist;
          bestIdx = idx;
        }
      });

      if (bestIdx >= 0 && bestDist <= RECOGNITION_TO_TRACK_MATCH_PX) {
        usedTrackIndexes.add(bestIdx);
        const track = tracks[bestIdx];
        tracks[bestIdx] = {
          ...track,
          label: result.name || track.label || 'Unknown',
          color: result.student_id ? '#00ff00' : '#ffaa00',
          studentId: result.student_id ?? null,
          score: Number(result.score || 0),
          lastRecognizedAt: now,
        };
      }
    });

    trackedFacesRef.current = tracks;
  }

  const runLocalDetection = useCallback(async () => {
    if (!isRunning || !hasLocalDetectorRef.current) return;
    if (isLocalDetectingRef.current) return;

    const now = Date.now();
    if (now - lastLocalDetectAtRef.current < LOCAL_DETECT_INTERVAL_MS) return;

    const video = videoRef.current;
    if (!video || video.readyState < 2) return;

    isLocalDetectingRef.current = true;
    lastLocalDetectAtRef.current = now;

    try {
      const detector = faceDetectorRef.current;
      if (!detector) return;

      const faces = await detector.detect(video);
      const detections = (faces || []).map((face) => {
        const box = face.boundingBox || {};
        return {
          x: Number(box.x || 0),
          y: Number(box.y || 0),
          w: Number(box.width || 0),
          h: Number(box.height || 0),
        };
      });

      if (detections.length > 0) {
        lastDetectedAtRef.current = Date.now();
      }

      mergeTrackedFaces(detections, {
        defaultColor: '#00bcd4',
        defaultLabel: 'Detecting...',
      });
    } catch (error) {
      console.warn('Local FaceDetector detect failed:', error);
    } finally {
      isLocalDetectingRef.current = false;
    }
  }, [isRunning]);

  function drawBoundingBoxes() {
    const canvas = drawCanvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;

    const width = video.videoWidth || 640;
    const height = video.videoHeight || 480;
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const now = Date.now();
    const tracks = (trackedFacesRef.current || []).filter(
      (track) => now - (track.lastSeenAt || now) <= TRACK_RETENTION_MS
    );

    if (!tracks.length) {
      lastDrawTsRef.current = now;
      return;
    }

    const drawDt = lastDrawTsRef.current ? (now - lastDrawTsRef.current) : 16;
    lastDrawTsRef.current = now;

    tracks.forEach((track) => {
      const age = now - (track.lastSeenAt || now);
      const predictionMs = Math.min(age, TRACK_PREDICTION_MAX_MS, drawDt);
      const predictedX = track.x + (track.vx * predictionMs) / 1000;
      const predictedY = track.y + (track.vy * predictionMs) / 1000;

      ctx.strokeStyle = track.color;
      ctx.lineWidth = 4;
      ctx.strokeRect(predictedX, predictedY, track.w, track.h);

      ctx.fillStyle = track.color;
      ctx.font = 'bold 18px Arial';
      const labelY = Math.max(18, predictedY - 10);
      ctx.fillText(track.label, predictedX, labelY);
    });

    trackedFacesRef.current = tracks;
    fpsFrameCountRef.current += 1;
  }

  const drawLoop = useCallback(() => {
    if (!isRunning) return;
    runLocalDetection();
    drawBoundingBoxes();
    rafIdRef.current = requestAnimationFrame(drawLoop);
  }, [isRunning, runLocalDetection]);

  const applyRecognitionResults = useCallback((results, latencyMs) => {
    const nowTs = Date.now();
    const normalizedResults = Array.isArray(results) ? results : [];

    // Stabilize UI decision per student across frames:
    // If a student was once AUTO_MARK later in the session, keep showing AUTO_MARK
    // even if some frames are stale / misclassified.
    const stabilizedResults = normalizedResults.map((result) => {
      if (!result || !result.student_id) return result;

      const sid = result.student_id;
      const prev = bestDecisionByStudentRef.current.get(sid);
      const curr = result.decision;
      const best = decisionRank(curr) >= decisionRank(prev) ? curr : prev;
      bestDecisionByStudentRef.current.set(sid, best);
      return { ...result, decision: best };
    });

    setLatestResults(stabilizedResults);
    if (stabilizedResults.length > 0) {
      lastDetectedAtRef.current = nowTs;
    }

    apiCallTimestampsRef.current.push(nowTs);
    apiCallTimestampsRef.current = apiCallTimestampsRef.current.filter((ts) => nowTs - ts <= 60000);

    latencySamplesRef.current.push(Math.max(0, Number(latencyMs || 0)));
    if (latencySamplesRef.current.length > MAX_LATENCY_SAMPLES) {
      latencySamplesRef.current.shift();
    }

    const avgLatency = latencySamplesRef.current.length
      ? latencySamplesRef.current.reduce((sum, value) => sum + value, 0) / latencySamplesRef.current.length
      : 0;

    setTelemetry((prev) => ({
      ...prev,
      apiCallsPerMin: apiCallTimestampsRef.current.length,
      lastLatencyMs: Math.max(0, Number(latencyMs || 0)),
      avgLatencyMs: avgLatency,
    }));

    const event = {
      ts: nowTs,
      faceCount: stabilizedResults.length,
      recognizedCount: stabilizedResults.filter((r) => !!r.student_id).length,
      autoMark: 0,
      manualReview: 0,
      reject: 0,
      skippedAlreadyMarked: 0,
    };

    stabilizedResults.forEach((result) => {
      // Backend may annotate frames/tracks that are skipped (e.g. throttled/dropped).
      // We still count "ALREADY_MARKED" decisions because the UI wants to reflect
      // recognition outcomes, not only DB inserts.
      if (result?.attendance_status === 'SKIPPED') {
        event.skippedAlreadyMarked += 1;
        return;
      }
      const decision = String(result.decision || 'REJECT');
      if (result?.student_id) {
        applyUniqueDecision(result.student_id, decision);
      }
      if (decision === 'AUTO_MARK') frameDecisionCountersRef.current.AUTO_MARK += 1;
      else if (decision === 'MANUAL_REVIEW') frameDecisionCountersRef.current.MANUAL_REVIEW += 1;
      else frameDecisionCountersRef.current.REJECT += 1;
      if (decision === 'AUTO_MARK') event.autoMark += 1;
      else if (decision === 'MANUAL_REVIEW') event.manualReview += 1;
      else event.reject += 1;
    });

    recognitionEventsRef.current.push(event);
    recomputeUniqueDecisionCounters();
    setDecisionStats({ ...decisionCountersRef.current });
    setFrameDecisionStats({ ...frameDecisionCountersRef.current });

    if (hasLocalDetectorRef.current) {
      applyRecognitionToLocalTracks(stabilizedResults);
    } else {
      updateTrackedFacesFromResults(stabilizedResults);
    }

    stabilizedResults.forEach((result) => {
      const { student_id, name, score } = result;
      if (!student_id || score < ATTENDANCE_LOG_THRESHOLD) return;
      if (attendedSet.current.has(student_id)) return;

      attendedSet.current.add(student_id);
      const markedAtMs = Date.now();

      const normalizedName = normalizePersonKey(name);
      const matched = expectedStudents.find((s) => normalizePersonKey(s.name) === normalizedName);
      const mssv = matched?.mssv || '';

      const logItem = {
        id: `${student_id}-${markedAtMs}`,
        studentId: student_id,
        name,
        mssv,
        status: 'Co mat',
        time: formatTimeHms(markedAtMs),
        markedAtMs,
      };
      setLog((prev) => [logItem, ...prev].slice(0, 30));

      setSessionAttendance((prev) => {
        const newMap = new Map(prev);
        newMap.set(student_id, {
          mssv,
          name: name,
          status: 'Có mặt',
          markedAtMs,
        });
        return newMap;
      });

      showAttendanceToast(name || `ID ${student_id}`);
    });
  }, [expectedStudents, showAttendanceToast]);

  const ensureRecognizeSocket = useCallback(() => {
    if (!isRunning) return null;

    const existing = wsRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return existing;
    }

    if (!sessionIdRef.current) {
      sessionIdRef.current = `sess-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    }
    const wsUrl = buildRealtimeWsUrl(sessionIdRef.current);
    if (!wsUrl) return null;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onclose = () => {
        setWsConnected(false);
        wsRef.current = null;
      };

      ws.onerror = () => {
        setWsConnected(false);
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type !== 'frame_result') return;

          const frameId = payload.frame_id;
          const sentAt = frameId ? pendingWsFramesRef.current.get(frameId) : null;
          if (frameId) pendingWsFramesRef.current.delete(frameId);
          const latency = sentAt ? performance.now() - sentAt : 0;

          // Drop stale/out-of-order results to avoid "drawing the past" when
          // frames backlog and arrive in bursts.
          if (sentAt && sentAt < lastWsAppliedSentAtRef.current) {
            return;
          }
          if (sentAt) lastWsAppliedSentAtRef.current = sentAt;

          const tracks = Array.isArray(payload.tracks) ? payload.tracks : [];
          const now = Date.now();
          const video = videoRef.current;
          const videoWidth = Number(video?.videoWidth || 640);
          const videoHeight = Number(video?.videoHeight || 480);
          const sentScale = Math.min(1, WS_SEND_MAX_WIDTH / Math.max(1, videoWidth));
          const sentWidth = Math.max(1, Math.round(videoWidth * sentScale));
          const sentHeight = Math.max(1, Math.round(videoHeight * sentScale));
          const sx = videoWidth / sentWidth;
          const sy = videoHeight / sentHeight;

          // If we have local FaceDetector running, keep bbox motion smooth locally
          // and only apply server recognition results (labels/ids).
          // If not, fallback to server-provided bboxes.
          if (!hasLocalDetectorRef.current) {
            trackedFacesRef.current = tracks
              .filter((t) => t?.bbox)
              .map((t) => {
                const bbox = t.bbox || {};
                const result = t.result || {};
                const studentId = result.student_id ?? null;
                return {
                  id: t.track_id,
                  // Backend detects on resized frame; map bbox back to display space.
                  x: Number(bbox.x || 0) * sx,
                  y: Number(bbox.y || 0) * sy,
                  w: Number(bbox.w || 0) * sx,
                  h: Number(bbox.h || 0) * sy,
                  label: result.name || 'Detecting...',
                  color: studentId ? '#00ff00' : '#00bcd4',
                  studentId,
                  score: Number(result.score || 0),
                  decision: result.decision || undefined,
                  vx: 0,
                  vy: 0,
                  lastSeenAt: now,
                };
              });
          }

          const results = tracks
            .filter((t) => t?.bbox && t?.result)
            .map((t) => ({
              ...t.result,
              bbox: {
                x: Number(t.bbox.x || 0) * sx,
                y: Number(t.bbox.y || 0) * sy,
                w: Number(t.bbox.w || 0) * sx,
                h: Number(t.bbox.h || 0) * sy,
                confidence: Number(t.bbox.confidence || 0),
              },
              track_id: t.track_id,
            }));

          applyRecognitionResults(results, latency);
        } catch (error) {
          console.error('WS message parse error:', error);
        }
      };

      return ws;
    } catch (error) {
      console.error('WS connect error:', error);
      return null;
    }
  }, [isRunning, applyRecognitionResults]);

  const processRecognition = useCallback(async () => {
    if (!isRunning) return;

    const now = Date.now();
    if (isProcessingRef.current) return;
    if (now - lastRunAtRef.current < RECOGNITION_INTERVAL_MS) return;

    const motion = measureMotion();
    const hasRecentFace = (now - lastDetectedAtRef.current) <= TRACK_RETENTION_MS;
    const mustSend = (now - lastApiSentAtRef.current) >= FORCE_SEND_INTERVAL_MS;
    const shouldSend = mustSend || hasRecentFace || motion.isMotion;

    if (!shouldSend) return;

    isProcessingRef.current = true;
    lastRunAtRef.current = now;
    lastApiSentAtRef.current = now;

    const blob = await captureFrame();
    if (!blob) {
      isProcessingRef.current = false;
      return;
    }

    try {
      const ws = ensureRecognizeSocket();
      if (ws && ws.readyState === WebSocket.OPEN) {
        if (pendingWsFramesRef.current.size >= WS_MAX_PENDING_FRAMES) {
          isProcessingRef.current = false;
          return;
        }

        const frameId = `f-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
        const imageData = await blobToDataUrl(blob);
        pendingWsFramesRef.current.set(frameId, performance.now());

        ws.send(JSON.stringify({
          type: 'frame',
          frame_id: frameId,
          image: imageData,
        }));
      } else {
        const requestStart = performance.now();
        const formData = new FormData();
        formData.append('file', blob, 'frame.jpg');

        const res = await apiFetch('/recognize', {
          method: 'POST',
          body: formData,
        });

        if (res.ok) {
          const json = await res.json();
          const results = Array.isArray(json?.data) ? json.data : [];
          applyRecognitionResults(results, performance.now() - requestStart);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      isProcessingRef.current = false;
    }
  }, [
    isRunning,
    measureMotion,
    captureFrame,
    ensureRecognizeSocket,
    blobToDataUrl,
    applyRecognitionResults,
  ]);

  useEffect(() => {
    if (!isRunning) return undefined;

    const timer = setInterval(() => {
      const frameCount = fpsFrameCountRef.current;
      fpsFrameCountRef.current = 0;
      setTelemetry((prev) => ({
        ...prev,
        fps: frameCount,
      }));

      telemetryTimelineRef.current.push({
        ts: Date.now(),
        fps: frameCount,
        apiCallsPerMin: apiCallTimestampsRef.current.length,
        lastLatencyMs: telemetry.lastLatencyMs,
        avgLatencyMs: telemetry.avgLatencyMs,
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isRunning, telemetry.avgLatencyMs, telemetry.lastLatencyMs]);

  const exportSessionJson = useCallback(() => {
    const payload = {
      meta: {
        startedAt: sessionStartedAtRef.current,
        exportedAt: new Date().toISOString(),
        recognitionIntervalMs: RECOGNITION_INTERVAL_MS,
      },
      telemetryTimeline: telemetryTimelineRef.current,
      recognitionEvents: recognitionEventsRef.current,
      latencySamplesMs: latencySamplesRef.current,
      decisionTotalsUnique: decisionCountersRef.current,
      decisionTotalsPerFrame: frameDecisionCountersRef.current,
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `session_metrics_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const exportSessionMetricsXlsx = useCallback(() => {
    const telemetryRows = telemetryTimelineRef.current.map((row) => ({
      timestamp: new Date(row.ts).toISOString(),
      fps: row.fps,
      api_calls_per_min: row.apiCallsPerMin,
      last_latency_ms: Number(row.lastLatencyMs || 0).toFixed(2),
      avg_latency_ms: Number(row.avgLatencyMs || 0).toFixed(2),
    }));

    const eventRows = recognitionEventsRef.current.map((row) => ({
      timestamp: new Date(row.ts).toISOString(),
      faces: row.faceCount,
      recognized: row.recognizedCount,
      auto_mark: row.autoMark,
      manual_review: row.manualReview,
      reject: row.reject,
    }));

    const decisionRows = [
      { decision: 'AUTO_MARK', unique_students: decisionCountersRef.current.AUTO_MARK, per_frame: frameDecisionCountersRef.current.AUTO_MARK },
      { decision: 'MANUAL_REVIEW', unique_students: decisionCountersRef.current.MANUAL_REVIEW, per_frame: frameDecisionCountersRef.current.MANUAL_REVIEW },
      { decision: 'REJECT', unique_students: decisionCountersRef.current.REJECT, per_frame: frameDecisionCountersRef.current.REJECT },
    ];

    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(telemetryRows), 'Telemetry');
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(eventRows), 'RecognitionEvents');
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(decisionRows), 'DecisionTotals');
    XLSX.writeFile(wb, `session_metrics_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.xlsx`);
  }, []);

  // Real-time loop theo interval để tránh dồn request
  useEffect(() => {
    if (!isRunning) return undefined;

    processRecognition();
    const timer = setInterval(() => {
      processRecognition();
    }, RECOGNITION_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [isRunning, processRecognition]);

  // Draw loop chạy riêng để overlay luôn mượt, không phụ thuộc nhịp gọi API
  useEffect(() => {
    if (!isRunning) {
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
      return undefined;
    }

    initLocalDetector();
    rafIdRef.current = requestAnimationFrame(drawLoop);
    return () => {
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, [isRunning, drawLoop, initLocalDetector]);

  // ==================== TOGGLE BẮT ĐẦU / DỪNG ====================
  async function toggleAttendance() {
    if (!isRunning) {
      const media = await startCamera();
      if (!media) return;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      pendingWsFramesRef.current.clear();
      lastWsAppliedSentAtRef.current = 0;
      setWsConnected(false);
      sessionIdRef.current = `sess-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
      setIsRunning(true);
      sessionStartedAtRef.current = new Date().toISOString();
      exportedAttendanceExcelRef.current = false;
      try {
        sessionStorage.setItem(ATTENDANCE_SESSION_RUNNING_KEY, '1');
      } catch (_) {
        // ignore
      }
      attendedSet.current.clear();        // Reset phiên mới
      bestDecisionByStudentRef.current.clear();
      setLog([]);
      setSessionAttendance(new Map());
      setToast(null);
      lastRunAtRef.current = 0;
      trackedFacesRef.current = [];
      lastDrawTsRef.current = 0;
      fpsFrameCountRef.current = 0;
      apiCallTimestampsRef.current = [];
      latencySamplesRef.current = [];
      telemetryTimelineRef.current = [];
      decisionCountersRef.current = { AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 };
      decisionSetsRef.current = { AUTO_MARK: new Set(), MANUAL_REVIEW: new Set(), REJECT: new Set() };
      frameDecisionCountersRef.current = { AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 };
      recognitionEventsRef.current = [];
      prevMotionSampleRef.current = null;
      lastApiSentAtRef.current = 0;
      lastDetectedAtRef.current = 0;
      lastLocalDetectAtRef.current = 0;
      ensureRecognizeSocket();
      setLatestResults([]);
      setTelemetry({ fps: 0, apiCallsPerMin: 0, lastLatencyMs: 0, avgLatencyMs: 0 });
      setDecisionStats({ AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 });
      setFrameDecisionStats({ AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 });
    } else {
      setStopConfirmOpen(true);
    }
  }

  const stopSessionNow = useCallback(() => {
    try {
      sessionStorage.setItem(ATTENDANCE_SESSION_RUNNING_KEY, '0');
    } catch (_) {
      // ignore
    }
    setIsRunning(false);
    if (stream) stream.getTracks().forEach(t => t.stop());
    setStream(null);
    trackedFacesRef.current = [];
    lastDrawTsRef.current = 0;
    fpsFrameCountRef.current = 0;
    prevMotionSampleRef.current = null;
    lastApiSentAtRef.current = 0;
    lastDetectedAtRef.current = 0;
    lastLocalDetectAtRef.current = 0;
    pendingWsFramesRef.current.clear();
    decisionCountersRef.current = { AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 };
    decisionSetsRef.current = { AUTO_MARK: new Set(), MANUAL_REVIEW: new Set(), REJECT: new Set() };
    frameDecisionCountersRef.current = { AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 };
    bestDecisionByStudentRef.current.clear();
    lastWsAppliedSentAtRef.current = 0;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setWsConnected(false);
    sessionIdRef.current = null;

    const drawCanvas = drawCanvasRef.current;
    if (drawCanvas) {
      const ctx = drawCanvas.getContext('2d');
      ctx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
    }
  }, [stream]);

  // ==================== 3. IMPORT EXCEL & XUẤT CSV ====================
  const handleImportExcel = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
      const data = evt.target.result;
      const workbook = XLSX.read(data, { type: 'binary' });
      const sheet = workbook.Sheets[workbook.SheetNames[0]];
      const json = XLSX.utils.sheet_to_json(sheet);

      function normalizeHeaderKey(value) {
        return String(value || '')
          .trim()
          .toLowerCase()
          .normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '')
          .replace(/đ/g, 'd')
          .replace(/\s+/g, ' ');
      }

      function pickField(row, candidates) {
        if (!row || typeof row !== 'object') return '';
        const entries = Object.entries(row);
        for (const cand of candidates) {
          const candKey = normalizeHeaderKey(cand);
          const found = entries.find(([k]) => normalizeHeaderKey(k) === candKey);
          if (found) {
            const v = found[1];
            if (v !== undefined && v !== null && String(v).trim() !== '') return String(v).trim();
          }
        }
        return '';
      }

      // Flexible columns:
      // - MSSV: MSSV / Mssv / MSV / MaSV / Mã SV / Student ID ...
      // - Name: Họ và tên / Ho va ten / Name / Full name ...
      const students = json
        .map((row) => {
          const mssv = pickField(row, [
            'MSSV',
            'MSV',
            'MaSV',
            'Mã SV',
            'Mã sinh viên',
            'Student ID',
            'StudentID',
            'ID',
          ]);
          const name = pickField(row, [
            'Họ và tên',
            'Ho va ten',
            'Họ tên',
            'Ho ten',
            'Full name',
            'Fullname',
            'Name',
            'Tên',
          ]);
          return { mssv, name };
        })
        .filter((s) => s.name);

      setExpectedStudents(students);
      alert(`Đã import ${students.length} sinh viên từ Excel`);
    };
    reader.readAsBinaryString(file);
  };

  const exportAttendanceCSV = () => {
    const sessionStartedAtIso = sessionStartedAtRef.current;
    const sessionStart = sessionStartedAtIso ? new Date(sessionStartedAtIso) : new Date();
    const sessionStartLabel = formatTimeHms(sessionStart);

    const attendedRows = Array.from(sessionAttendance.entries()).map(([studentId, info]) => {
      const markedAtMs = Number(info?.markedAtMs || 0) || null;
      const markedAtLabel = markedAtMs ? formatTimeHms(markedAtMs) : '';
      const deltaLabel = markedAtMs ? formatSinceStartMs(markedAtMs - sessionStart.getTime()) : '';
      return {
        student_id: studentId,
        mssv: info?.mssv || '',
        name: info?.name || '',
        status: info?.status || 'Có mặt',
        session_start: sessionStartLabel,
        marked_at: markedAtLabel,
        since_start: deltaLabel,
      };
    });

    const attendedByMssv = new Map(
      attendedRows
        .filter((row) => row.mssv)
        .map((row) => [String(row.mssv).trim(), row])
    );
    const attendedByNormName = new Map(
      attendedRows
        .filter((row) => row.name)
        .map((row) => [normalizePersonKey(row.name), row])
    );

    let finalList = [];

    if (expectedStudents.length > 0) {
      finalList = expectedStudents.map((student) => {
        const mssvKey = String(student.mssv || '').trim();
        const normName = normalizePersonKey(student.name);
        const attended =
          (mssvKey && attendedByMssv.get(mssvKey)) ||
          (normName && attendedByNormName.get(normName));

        return {
          MSSV: student.mssv,
          'Họ và tên': student.name,
          'Trạng thái': attended ? 'Có mặt' : 'Vắng',
          'Giờ mở phiên': sessionStartLabel,
          'Giờ điểm danh': attended?.marked_at || '',
          'Thời gian kể từ mở phiên': attended?.since_start || '',
        };
      });

      // Append attended students not found in expected list (so exports never "lose" them).
      const expectedMssv = new Set(expectedStudents.map((s) => String(s.mssv || '').trim()).filter(Boolean));
      const expectedNames = new Set(expectedStudents.map((s) => normalizePersonKey(s.name)).filter(Boolean));
      const extras = attendedRows.filter((row) => {
        const mssvKey = String(row.mssv || '').trim();
        const nameKey = normalizePersonKey(row.name);
        if (mssvKey && expectedMssv.has(mssvKey)) return false;
        if (nameKey && expectedNames.has(nameKey)) return false;
        return true;
      });

      if (extras.length > 0) {
        finalList.push({});
        finalList.push({ MSSV: '', 'Họ và tên': '--- Ngoài danh sách import ---', 'Trạng thái': '' });
        extras.forEach((row) => {
          finalList.push({
            MSSV: row.mssv || '',
            'Họ và tên': row.name || `ID ${row.student_id}`,
            'Trạng thái': 'Có mặt',
            'Giờ mở phiên': sessionStartLabel,
            'Giờ điểm danh': row.marked_at || '',
            'Thời gian kể từ mở phiên': row.since_start || '',
          });
        });
      }
    } else {
      // No expected list imported: export only attended students.
      finalList = attendedRows.map((row) => ({
        MSSV: row.mssv || '',
        'Họ và tên': row.name || `ID ${row.student_id}`,
        'Trạng thái': 'Có mặt',
        'Giờ mở phiên': sessionStartLabel,
        'Giờ điểm danh': row.marked_at || '',
        'Thời gian kể từ mở phiên': row.since_start || '',
      }));
    }

    const worksheet = XLSX.utils.json_to_sheet(finalList);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "DiemDanh");
    XLSX.writeFile(workbook, `DiemDanh_${new Date().toISOString().slice(0,10)}.xlsx`);
    exportedAttendanceExcelRef.current = true;
  };

  return (
    <div className="panel-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '20px' }}>
      <ConfirmDialog
        open={stopConfirmOpen}
        title={exportedAttendanceExcelRef.current ? 'Xong xuôi rồi chứ?' : 'Khoan khoan…'}
        message={
          exportedAttendanceExcelRef.current
            ? 'Bạn đã xuất file Excel. Bạn chắc chắn muốn đóng phiên điểm danh chứ?'
            : 'Bạn chưa xuất file Excel. Đóng phiên bây giờ có thể làm bạn quên mất việc xuất file.'
        }
        confirmText={exportedAttendanceExcelRef.current ? 'Đóng phiên' : 'Vẫn đóng phiên'}
        cancelText="Tiếp tục điểm danh"
        tone={exportedAttendanceExcelRef.current ? 'info' : 'warning'}
        onCancel={() => setStopConfirmOpen(false)}
        onConfirm={() => {
          setStopConfirmOpen(false);
          stopSessionNow();
        }}
      />
      {/* ==================== CAMERA SECTION ==================== */}
      <section className="panel-card camera-panel">
        <h2>📸 Điểm danh realtime</h2>

        <div style={{ position: 'relative', width: '100%', maxWidth: '640px' }}>
          <video
            ref={videoRef}
            className="camera-preview"
            muted
            playsInline
            style={{ width: '100%', borderRadius: '12px' }}
          />
          {toast && (
            <div key={toast.id} className="attendance-toast" role="status" aria-live="polite">
              <div className="attendance-toast-title">Điểm danh thành công</div>
              <div className="attendance-toast-message">{toast.message}</div>
            </div>
          )}
          <canvas
            ref={drawCanvasRef}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              pointerEvents: 'none',
              borderRadius: '12px'
            }}
          />
        </div>
        <canvas ref={canvasRef} hidden />

        <div className="button-row" style={{ marginTop: '15px' }}>
          <button
            className={`btn ${isRunning ? 'btn-danger' : 'btn-primary'}`}
            onClick={toggleAttendance}
            style={{ padding: '12px 28px', fontSize: '16px' }}
          >
            {isRunning ? '⏹️ Dừng phiên' : '▶️ Bắt đầu điểm danh'}
          </button>
        </div>
      </section>

      {/* ==================== LOG + IMPORT/EXPORT SECTION ==================== */}
      <section className="panel-card log-panel" style={{ background: '#f8f9fa', borderRadius: '12px', padding: '20px' }}>
        <h3>📊 Telemetry realtime</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '14px' }}>
          <div style={{ background: '#fff', border: '1px solid #ddd', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#666' }}>FPS overlay</div>
            <div style={{ fontWeight: 700, fontSize: '18px' }}>{telemetry.fps}</div>
          </div>
          <div style={{ background: '#fff', border: '1px solid #ddd', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#666' }}>API calls / phút</div>
            <div style={{ fontWeight: 700, fontSize: '18px' }}>{telemetry.apiCallsPerMin}</div>
          </div>
          <div style={{ background: '#fff', border: '1px solid #ddd', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#666' }}>Latency gần nhất</div>
            <div style={{ fontWeight: 700, fontSize: '18px' }}>{telemetry.lastLatencyMs.toFixed(1)} ms</div>
          </div>
          <div style={{ background: '#fff', border: '1px solid #ddd', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#666' }}>Latency trung bình</div>
            <div style={{ fontWeight: 700, fontSize: '18px' }}>{telemetry.avgLatencyMs.toFixed(1)} ms</div>
          </div>
        </div>

        <div style={{ marginBottom: '8px', fontSize: '12px', color: '#666' }}>
          Thống kê theo <strong>sinh viên duy nhất</strong> (unique) trong phiên
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px', marginBottom: '14px' }}>
          <div style={{ background: '#e8f5e9', border: '1px solid #c8e6c9', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#2e7d32' }}>AUTO_MARK (unique)</div>
            <div style={{ fontWeight: 700, fontSize: '18px', color: '#1b5e20' }}>{decisionStats.AUTO_MARK}</div>
          </div>
          <div style={{ background: '#fff8e1', border: '1px solid #ffecb3', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#f57f17' }}>MANUAL_REVIEW (unique)</div>
            <div style={{ fontWeight: 700, fontSize: '18px', color: '#ef6c00' }}>{decisionStats.MANUAL_REVIEW}</div>
          </div>
          <div style={{ background: '#ffebee', border: '1px solid #ffcdd2', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#c62828' }}>REJECT (unique)</div>
            <div style={{ fontWeight: 700, fontSize: '18px', color: '#b71c1c' }}>{decisionStats.REJECT}</div>
          </div>
        </div>

        <div style={{ marginBottom: '8px', fontSize: '12px', color: '#666' }}>
          Thống kê theo <strong>từng frame/kết quả</strong> (per-frame) trong phiên
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px', marginBottom: '14px' }}>
          <div style={{ background: '#e8f5e9', border: '1px solid #c8e6c9', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#2e7d32' }}>AUTO_MARK (per-frame)</div>
            <div style={{ fontWeight: 700, fontSize: '18px', color: '#1b5e20' }}>{frameDecisionStats.AUTO_MARK}</div>
          </div>
          <div style={{ background: '#fff8e1', border: '1px solid #ffecb3', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#f57f17' }}>MANUAL_REVIEW (per-frame)</div>
            <div style={{ fontWeight: 700, fontSize: '18px', color: '#ef6c00' }}>{frameDecisionStats.MANUAL_REVIEW}</div>
          </div>
          <div style={{ background: '#ffebee', border: '1px solid #ffcdd2', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#c62828' }}>REJECT (per-frame)</div>
            <div style={{ fontWeight: 700, fontSize: '18px', color: '#b71c1c' }}>{frameDecisionStats.REJECT}</div>
          </div>
        </div>

        <h3>Top-3  confidence</h3>
        <div style={{ maxHeight: '220px', overflowY: 'auto', marginBottom: '14px' }}>
          {latestResults.length === 0 ? (
            <p style={{ color: '#888', margin: '8px 0 0' }}>Chưa có dữ liệu nhận diện.</p>
          ) : (
            latestResults.map((result, idx) => {
              const decisionColor =
                result.decision === 'AUTO_MARK' ? '#198754' :
                result.decision === 'MANUAL_REVIEW' ? '#f59f00' : '#dc3545';

              return (
                <div key={`face-${idx}`} style={{ background: '#fff', border: '1px solid #ddd', borderRadius: '8px', padding: '10px', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong>{result.name || 'Unknown'}</strong>
                    <span style={{ color: decisionColor, fontWeight: 700, fontSize: '12px' }}>{result.decision || 'REJECT'}</span>
                  </div>
                  <small style={{ color: '#666' }}>
                    Score: {Number(result.score || 0).toFixed(4)} | Liveness: {result?.liveness?.is_real ? 'Real' : 'Spoof/Unknown'}
                  </small>

                  {(result.top_candidates || []).map((cand) => {
                    const barWidth = Math.max(0, Math.min(100, Number(cand.score || 0) * 100));
                    return (
                      <div key={`cand-${idx}-${cand.rank}`} style={{ marginTop: '7px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                          <span>#{cand.rank} {cand.name || 'Unknown'}</span>
                          <span>{Number(cand.score || 0).toFixed(4)}</span>
                        </div>
                        <div style={{ width: '100%', background: '#e9ecef', height: '8px', borderRadius: '6px', overflow: 'hidden' }}>
                          <div style={{ width: `${barWidth}%`, height: '8px', background: '#0d6efd' }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        <h3>📋 Log điểm danh</h3>
        <div
          style={{
            height: '420px',
            overflowY: 'auto',
            background: '#fff',
            borderRadius: '8px',
            padding: '12px',
            border: '1px solid #ddd'
          }}
        >
          {log.length === 0 ? (
            <p style={{ color: '#888', textAlign: 'center', marginTop: '80px' }}>
              Chưa có sinh viên nào được điểm danh
            </p>
          ) : (
            log.map((entry) => (
              <div key={entry.id} className="attendance-log-item">
                <div className="attendance-log-title">✅ {entry.name}</div>
                <div className="attendance-log-meta">
                  <span>{entry.mssv ? `MSSV: ${entry.mssv}` : `ID: ${entry.studentId}`}</span>
                  <span>{entry.time}</span>
                </div>
              </div>
            ))
          )}
        </div>

        <div style={{ marginTop: '20px' }}>
          <h4>Quản lý file điểm danh</h4>
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={handleImportExcel}
            style={{ marginBottom: '12px', display: 'block' }}
          />
          <button onClick={exportAttendanceCSV} className="btn btn-success" style={{ width: '100%' }}>
            📤 Xuất file Excel điểm danh
          </button>
        </div>

        <div style={{ marginTop: '16px' }}>
          <h4>Dữ liệu nghiên cứu</h4>
          <div style={{ display: 'grid', gap: '8px' }}>
            <button onClick={exportSessionJson} className="btn btn-primary" style={{ width: '100%' }}>
              🧪 Xuất JSON phiên đo
            </button>
            <button onClick={exportSessionMetricsXlsx} className="btn btn-ghost" style={{ width: '100%' }}>
              📈 Xuất Excel telemetry
            </button>
          </div>
        </div>

        {expectedStudents.length > 0 && (
          <small style={{ display: 'block', marginTop: '10px', color: '#666' }}>
            Đã tải danh sách {expectedStudents.length} sinh viên từ Excel
          </small>
        )}
      </section>
    </div>
  );
}

export default AttendancePanel;