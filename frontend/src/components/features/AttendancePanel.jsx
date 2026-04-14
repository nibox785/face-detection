import { useEffect, useRef, useState } from 'react';
import { apiFetch, API_BASE } from '../../api/apiClient';

function AttendancePanel() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const drawCanvasRef = useRef(null);
  
  const [isRunning, setIsRunning] = useState(false);
  const [log, setLog] = useState([]);
  const [intervalMs, setIntervalMs] = useState(450);
  const [stream, setStream] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const lastRecognitionRef = useRef(new Map());
  const captureMetaRef = useRef({ width: 0, height: 0 });

  // Cleanup camera khi component unmount
  useEffect(() => {
    return () => {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
    };
  }, [stream]);

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      addLog('Trình duyệt không hỗ trợ camera', 'error');
      return null;
    }

    try {
      const media = await navigator.mediaDevices.getUserMedia({ 
        video: { facingMode: "user" } 
      });
      videoRef.current.srcObject = media;
      await videoRef.current.play();
      
      // Set canvas size when video metadata is loaded
      videoRef.current.onloadedmetadata = () => {
        drawCanvasRef.current.width = videoRef.current.videoWidth;
        drawCanvasRef.current.height = videoRef.current.videoHeight;
      };

      setStream(media);
      addLog('Camera đã mở thành công', 'success');
      return media;
    } catch (err) {
      console.error(err);
      addLog('Không thể mở camera. Vui lòng kiểm tra quyền truy cập.', 'error');
      return null;
    }
  }

  function addLog(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const prefix = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
    
    setLog(prev => [{
      id: Date.now(),
      text: `${prefix} ${timestamp} - ${message}`,
      type
    }, ...prev].slice(0, 50)); // Giới hạn chỉ giữ 50 dòng log mới nhất
  }

  function drawBoundingBoxes(recognitionResults) {
    const drawCanvas = drawCanvasRef.current;
    const video = videoRef.current;
    if (!drawCanvas || !video || video.videoWidth === 0) return;

    // Set canvas size to match video only when needed.
    if (drawCanvas.width !== video.videoWidth || drawCanvas.height !== video.videoHeight) {
      drawCanvas.width = video.videoWidth;
      drawCanvas.height = video.videoHeight;
    }

    const ctx = drawCanvas.getContext('2d');
    ctx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);

    const sourceWidth = captureMetaRef.current.width || drawCanvas.width;
    const sourceHeight = captureMetaRef.current.height || drawCanvas.height;
    const scaleX = drawCanvas.width / sourceWidth;
    const scaleY = drawCanvas.height / sourceHeight;

    recognitionResults.forEach((result) => {
      if (!result.bbox) return;

      const { x, y, w, h } = result.bbox;
      const sx = Math.round(x * scaleX);
      const sy = Math.round(y * scaleY);
      const sw = Math.round(w * scaleX);
      const sh = Math.round(h * scaleY);
      const color = result.student_id ? '#00ff00' : '#ff0000'; // Green = recognized, Red = unknown

      // Draw bounding box
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.strokeRect(sx, sy, sw, sh);

      // Always draw label above box (recognized name or Unknown)
      const label = result.name || 'Unknown';
      ctx.font = 'bold 16px Arial';
      const labelWidth = Math.max(100, ctx.measureText(label).width + 16);
      const labelX = sx;
      const labelY = Math.max(0, sy - 30);

      ctx.fillStyle = color;
      ctx.fillRect(labelX, labelY, labelWidth, 28);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(label, labelX + 8, labelY + 19);
    });
  }

  async function captureFrame() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.videoWidth === 0) return null;

    const maxCaptureWidth = 640;
    const srcWidth = video.videoWidth;
    const srcHeight = video.videoHeight;
    const scale = srcWidth > maxCaptureWidth ? maxCaptureWidth / srcWidth : 1;
    const targetWidth = Math.max(1, Math.round(srcWidth * scale));
    const targetHeight = Math.max(1, Math.round(srcHeight * scale));

    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise((resolve) => {
      canvas.toBlob((blob) => {
        if (!blob) {
          resolve(null);
          return;
        }
        resolve({ blob, width: targetWidth, height: targetHeight });
      }, 'image/jpeg', 0.82);
    });
  }

  async function doAttendance() {
    if (isProcessing) return;

    setIsProcessing(true);
    const frameData = await captureFrame();

    if (!frameData || !frameData.blob) {
      addLog('Không thể chụp ảnh từ camera', 'error');
      setIsProcessing(false);
      return;
    }

    captureMetaRef.current = {
      width: frameData.width,
      height: frameData.height,
    };

    const formData = new FormData();
    formData.append('file', frameData.blob, 'attendance.jpg');

    try {
      const res = await apiFetch('/recognize', { 
        method: 'POST', 
        body: formData 
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const json = await res.json();

      if (!json.data || json.data.length === 0) {
        addLog(json.message || 'Không phát hiện được khuôn mặt nào', 'warning');
        drawBoundingBoxes([]); // Clear boxes
        setIsProcessing(false);
        return;
      }

      // Vẽ bounding boxes và tên trên canvas
      drawBoundingBoxes(json.data);

      // Chỉ log khi nhận diện ổn định hoặc thay đổi trạng thái để tránh nhấp nháy.
      const now = Date.now();
      json.data.forEach((item, index) => {
        const key = item.student_id ? `student:${item.student_id}` : `unknown:${index}`;
        const previous = lastRecognitionRef.current.get(key) || { name: null, time: 0 };
        const labelName = item.student_id ? item.name : 'Unknown';

        if (previous.name !== labelName || now - previous.time > 3000) {
          if (item.student_id) {
            addLog(`✓ ${item.name} (${item.score})`, 'success');
          } else {
            addLog(`? Unknown (${item.score})`, 'warning');
          }
          lastRecognitionRef.current.set(key, { name: labelName, time: now });
        }
      });

    } catch (err) {
      console.error(err);
      addLog(`Lỗi khi điểm danh: ${err.message}`, 'error');
    } finally {
      setIsProcessing(false);
    }
  }

  async function toggleAttendance() {
    if (!isRunning) {
      const media = await startCamera();
      if (!media) return;

      setIsRunning(true);
      const timer = setInterval(doAttendance, intervalMs);
      videoRef.current.dataset.timerId = timer;
      addLog('Bắt đầu điểm danh tự động', 'success');
    } else {
      const timerId = Number(videoRef.current?.dataset.timerId);
      if (timerId) clearInterval(timerId);

      setIsRunning(false);
      setIsProcessing(false);

      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
        setStream(null);
      }

      addLog('Đã dừng điểm danh', 'info');
    }
  }

  async function exportCsv() {
    try {
      const response = await apiFetch('/attendance/export', {
        method: 'GET',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `attendance_report_${new Date().toISOString().slice(0,10)}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      addLog('Đã tải báo cáo CSV thành công', 'success');
    } catch (err) {
      console.error(err);
      addLog(`Lỗi xuất CSV: ${err.message}`, 'error');
    }
  }

  return (
    <div className="panel-grid">
      <section className="panel-card camera-panel">
        <h2>📸 Điểm danh bằng khuôn mặt</h2>
        
        <div style={{ position: 'relative', display: 'inline-block', width: '100%' }}>
          <video 
            ref={videoRef} 
            className="camera-preview" 
            muted 
            playsInline 
          />
          <canvas 
            ref={drawCanvasRef}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              pointerEvents: 'none',
            }}
          />
        </div>
        <canvas ref={canvasRef} hidden />

        <div className="button-row">
          <button 
            type="button" 
            className={`btn ${isRunning ? 'btn-danger' : 'btn-primary'}`}
            onClick={toggleAttendance}
            disabled={isProcessing}
          >
            {isRunning ? '⏹️ Dừng điểm danh' : '▶️ Bắt đầu điểm danh'}
          </button>

          <button 
            type="button" 
            className="btn btn-secondary"
            onClick={exportCsv}
          >
            📊 Xuất báo cáo CSV
          </button>
        </div>

        <div className="interval-control">
          <label>
            Chu kỳ quét ảnh (ms):
            <input
              type="number"
              value={intervalMs}
              min="250"
              step="100"
              onChange={(e) => setIntervalMs(Number(e.target.value))}
              disabled={isRunning}
            />
          </label>
          <small>{intervalMs}ms ≈ {(1000 / intervalMs).toFixed(1)} lần/giây</small>
        </div>
      </section>

      <section className="panel-card log-panel">
        <div className="log-header">
          <h3>Nhật ký hoạt động</h3>
          <button 
            className="btn btn-small btn-secondary" 
            onClick={() => setLog([])}
          >
            Xóa log
          </button>
        </div>
        
        <div className="log-box">
          {log.length === 0 ? (
            <p className="empty-log">Chưa có hoạt động nào. Hãy bắt đầu điểm danh...</p>
          ) : (
            log.map((entry) => (
              <div key={entry.id} className={`log-entry ${entry.type}`}>
                {entry.text}
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

export default AttendancePanel;