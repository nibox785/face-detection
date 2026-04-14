import { useEffect, useRef, useState, useCallback } from 'react';
import { apiFetch } from '../../api/apiClient';
import * as XLSX from 'xlsx';  

const RECOGNITION_INTERVAL_MS = 750;

function AttendancePanel() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const drawCanvasRef = useRef(null);
  const isProcessingRef = useRef(false);
  const lastRunAtRef = useRef(0);
  const toastTimerRef = useRef(null);

  const [isRunning, setIsRunning] = useState(false);
  const [log, setLog] = useState([]);
  const [stream, setStream] = useState(null);
  const [expectedStudents, setExpectedStudents] = useState([]); // từ file Excel import
  const [sessionAttendance, setSessionAttendance] = useState(new Map()); // student_id -> {mssv, name, status}
  const [toast, setToast] = useState(null);

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

  function drawBoundingBoxes(results) {
    const canvas = drawCanvasRef.current;
    const video = videoRef.current;
    if (!canvas || !results || !video) return;

    const width = video.videoWidth || 640;
    const height = video.videoHeight || 480;
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    results.forEach(result => {
      if (!result.bbox) return;
      const { x, y, w, h } = result.bbox;
      const color = result.student_id ? '#00ff00' : '#ffaa00';

      ctx.strokeStyle = color;
      ctx.lineWidth = 4;
      ctx.strokeRect(x, y, w, h);

      const label = result.name || `Unknown`;
      ctx.fillStyle = color;
      ctx.font = 'bold 18px Arial';
      ctx.fillText(label, x, y - 10);
    });
  }

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

    try {
      const res = await apiFetch('/recognize', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) return;
      const json = await res.json();
      const results = Array.isArray(json?.data) ? json.data : [];

      drawBoundingBoxes(results);

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

  // Real-time loop theo interval để tránh dồn request
  useEffect(() => {
    if (!isRunning) return undefined;

    processRecognition();
    const timer = setInterval(() => {
      processRecognition();
    }, RECOGNITION_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [isRunning, processRecognition]);

  // ==================== TOGGLE BẮT ĐẦU / DỪNG ====================
  async function toggleAttendance() {
    if (!isRunning) {
      const media = await startCamera();
      if (!media) return;
      setIsRunning(true);
      attendedSet.current.clear();        // Reset phiên mới
      setLog([]);
      setSessionAttendance(new Map());
      setToast(null);
      lastRunAtRef.current = 0;
    } else {
      setIsRunning(false);
      if (stream) stream.getTracks().forEach(t => t.stop());
      setStream(null);

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