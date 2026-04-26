import { useEffect, useRef, useState, useCallback } from 'react';
import { apiFetch } from '../../api/apiClient';
import * as XLSX from 'xlsx';  

const RECOGNITION_INTERVAL_MS = 700;
const TRACK_RETENTION_MS = 1400;
const TRACK_PREDICTION_MAX_MS = 650;
const TRACK_MATCH_DISTANCE_PX = 140;
const VELOCITY_DAMPING = 0.88;

const MAX_LATENCY_SAMPLES = 40;

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
  const decisionCountersRef = useRef({ AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 });
  const recognitionEventsRef = useRef([]);
  const sessionStartedAtRef = useRef(null);

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

  const attendedSet = useRef(new Set()); // Ngăn ghi log lặp lại trong cùng phiên

  // Cleanup camera
  useEffect(() => {
    return () => {
      if (stream) stream.getTracks().forEach(track => track.stop());
      if (toastTimerRef.current) {
        clearTimeout(toastTimerRef.current);
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

  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return null;

    const width = video.videoWidth || 640;
    const height = video.videoHeight || 480;

    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise(resolve => {
      canvas.toBlob(blob => resolve(blob), 'image/jpeg', 0.85);
    });
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

  function updateTrackedFaces(results) {
    const now = Date.now();
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
          vx,
          vy,
          lastSeenAt: now,
        });
      } else {
        next.push({
          id: `track-${now}-${Math.random().toString(16).slice(2, 8)}`,
          ...det,
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
      trackedFacesRef.current = [];
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
    drawBoundingBoxes();
    rafIdRef.current = requestAnimationFrame(drawLoop);
  }, [isRunning]);

  const processRecognition = useCallback(async () => {
    if (!isRunning) return;

    const now = Date.now();
    if (isProcessingRef.current) return;
    if (now - lastRunAtRef.current < RECOGNITION_INTERVAL_MS) return;

    isProcessingRef.current = true;
    lastRunAtRef.current = now;

    const blob = await captureFrame();
    if (!blob) {
      isProcessingRef.current = false;
      return;
    }

    const formData = new FormData();
    formData.append('file', blob, 'frame.jpg');
    const requestStart = performance.now();

    try {
      const res = await apiFetch('/recognize', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) return;
      const json = await res.json();
      const results = Array.isArray(json?.data) ? json.data : [];
      setLatestResults(results);

      const latency = Math.max(0, performance.now() - requestStart);
      const nowTs = Date.now();
      apiCallTimestampsRef.current.push(nowTs);
      apiCallTimestampsRef.current = apiCallTimestampsRef.current.filter((ts) => nowTs - ts <= 60000);

      latencySamplesRef.current.push(latency);
      if (latencySamplesRef.current.length > MAX_LATENCY_SAMPLES) {
        latencySamplesRef.current.shift();
      }

      const avgLatency = latencySamplesRef.current.length
        ? latencySamplesRef.current.reduce((sum, value) => sum + value, 0) / latencySamplesRef.current.length
        : 0;

      setTelemetry((prev) => ({
        ...prev,
        apiCallsPerMin: apiCallTimestampsRef.current.length,
        lastLatencyMs: latency,
        avgLatencyMs: avgLatency,
      }));

      const event = {
        ts: nowTs,
        faceCount: results.length,
        recognizedCount: results.filter((r) => !!r.student_id).length,
        autoMark: 0,
        manualReview: 0,
        reject: 0,
      };

      results.forEach((result) => {
        const decision = String(result.decision || 'REJECT');
        if (decision === 'AUTO_MARK') {
          decisionCountersRef.current.AUTO_MARK += 1;
          event.autoMark += 1;
        } else if (decision === 'MANUAL_REVIEW') {
          decisionCountersRef.current.MANUAL_REVIEW += 1;
          event.manualReview += 1;
        } else {
          decisionCountersRef.current.REJECT += 1;
          event.reject += 1;
        }
      });

      recognitionEventsRef.current.push(event);
      setDecisionStats({ ...decisionCountersRef.current });

      updateTrackedFaces(results);

      results.forEach(result => {
        const { student_id, name, score } = result;
        if (!student_id || score < 0.68) return; // ngưỡng an toàn

        // Chỉ ghi log 1 lần duy nhất trong phiên
        if (attendedSet.current.has(student_id)) return;

        attendedSet.current.add(student_id);

        const matched = expectedStudents.find(
          s => s.name?.trim().toLowerCase() === String(name || '').trim().toLowerCase()
        );
        const mssv = matched?.mssv || '';

        // Thêm log
        const logItem = {
          id: `${student_id}-${Date.now()}`,
          studentId: student_id,
          name,
          mssv,
          status: 'Co mat',
          time: new Date().toLocaleTimeString('vi-VN', { hour12: false })
        };
        setLog(prev => [logItem, ...prev].slice(0, 30)); // giữ tối đa 30 log

        // Lưu vào sessionAttendance
        setSessionAttendance(prev => {
          const newMap = new Map(prev);
          newMap.set(student_id, {
            mssv,
            name: name,
            status: 'Có mặt'
          });
          return newMap;
        });

        showAttendanceToast(name || `ID ${student_id}`);
      });
    } catch (e) {
      console.error(e);
    } finally {
      isProcessingRef.current = false;
    }
  }, [captureFrame, expectedStudents, isRunning, showAttendanceToast]);

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
      decisionTotals: decisionCountersRef.current,
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
      { decision: 'AUTO_MARK', count: decisionCountersRef.current.AUTO_MARK },
      { decision: 'MANUAL_REVIEW', count: decisionCountersRef.current.MANUAL_REVIEW },
      { decision: 'REJECT', count: decisionCountersRef.current.REJECT },
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

    rafIdRef.current = requestAnimationFrame(drawLoop);
    return () => {
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, [isRunning, drawLoop]);

  // ==================== TOGGLE BẮT ĐẦU / DỪNG ====================
  async function toggleAttendance() {
    if (!isRunning) {
      const media = await startCamera();
      if (!media) return;
      setIsRunning(true);
      sessionStartedAtRef.current = new Date().toISOString();
      attendedSet.current.clear();        // Reset phiên mới
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
      recognitionEventsRef.current = [];
      setLatestResults([]);
      setTelemetry({ fps: 0, apiCallsPerMin: 0, lastLatencyMs: 0, avgLatencyMs: 0 });
      setDecisionStats({ AUTO_MARK: 0, MANUAL_REVIEW: 0, REJECT: 0 });
    } else {
      setIsRunning(false);
      if (stream) stream.getTracks().forEach(t => t.stop());
      setStream(null);
      trackedFacesRef.current = [];
      lastDrawTsRef.current = 0;
      fpsFrameCountRef.current = 0;

      const drawCanvas = drawCanvasRef.current;
      if (drawCanvas) {
        const ctx = drawCanvas.getContext('2d');
        ctx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
      }
    }
  }

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

      // Giả sử cột Excel có: MSSV, Họ và tên (hoặc Name)
      const students = json.map(row => ({
        mssv: row['MSSV'] || row['mssv'] || '',
        name: row['Họ và tên'] || row['Name'] || row['name'] || ''
      })).filter(s => s.name);

      setExpectedStudents(students);
      alert(`Đã import ${students.length} sinh viên từ Excel`);
    };
    reader.readAsBinaryString(file);
  };

  const exportAttendanceCSV = () => {
    const finalList = expectedStudents.map(student => {
      // Tìm trong sessionAttendance theo tên (hoặc MSSV nếu có)
      const attended = Array.from(sessionAttendance.values()).find(
        a => a.name === student.name || (a.mssv && a.mssv === student.mssv)
      );

      return {
        MSSV: student.mssv,
        'Họ và tên': student.name,
        'Trạng thái': attended ? 'Có mặt' : 'Vắng'
      };
    });

    const worksheet = XLSX.utils.json_to_sheet(finalList);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "DiemDanh");
    XLSX.writeFile(workbook, `DiemDanh_${new Date().toISOString().slice(0,10)}.xlsx`);
  };

  return (
    <div className="panel-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '20px' }}>
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

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px', marginBottom: '14px' }}>
          <div style={{ background: '#e8f5e9', border: '1px solid #c8e6c9', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#2e7d32' }}>AUTO_MARK</div>
            <div style={{ fontWeight: 700, fontSize: '18px', color: '#1b5e20' }}>{decisionStats.AUTO_MARK}</div>
          </div>
          <div style={{ background: '#fff8e1', border: '1px solid #ffecb3', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#f57f17' }}>MANUAL_REVIEW</div>
            <div style={{ fontWeight: 700, fontSize: '18px', color: '#ef6c00' }}>{decisionStats.MANUAL_REVIEW}</div>
          </div>
          <div style={{ background: '#ffebee', border: '1px solid #ffcdd2', borderRadius: '8px', padding: '10px' }}>
            <div style={{ fontSize: '12px', color: '#c62828' }}>REJECT</div>
            <div style={{ fontWeight: 700, fontSize: '18px', color: '#b71c1c' }}>{decisionStats.REJECT}</div>
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