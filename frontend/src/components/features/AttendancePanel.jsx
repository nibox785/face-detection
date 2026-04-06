import { useEffect, useRef, useState } from 'react';
import { apiFetch, API_BASE } from '../../api/apiClient';

function AttendancePanel() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  
  const [isRunning, setIsRunning] = useState(false);
  const [log, setLog] = useState([]);
  const [intervalMs, setIntervalMs] = useState(3000);
  const [stream, setStream] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);

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

  async function captureFrame() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.videoWidth === 0) return null;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise((resolve) => {
      canvas.toBlob(resolve, 'image/jpeg', 0.85);
    });
  }

  async function doAttendance() {
    if (isProcessing) return;

    setIsProcessing(true);
    const blob = await captureFrame();

    if (!blob) {
      addLog('Không thể chụp ảnh từ camera', 'error');
      setIsProcessing(false);
      return;
    }

    const formData = new FormData();
    formData.append('file', blob, 'attendance.jpg');

    try {
      addLog('Đang gửi ảnh lên server...', 'info');

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
        setIsProcessing(false);
        return;
      }

      // Hiển thị tên sinh viên nếu có (từ backend trả về)
      json.data.forEach((item) => {
        if (item.student_id) {
          addLog(`Sinh viên ID ${item.student_id} điểm danh thành công (Score: ${item.score})`, 'success');
        } else {
          addLog(`Không nhận diện được khuôn mặt (Score: ${item.score})`, 'warning');
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
        
        <video 
          ref={videoRef} 
          className="camera-preview" 
          muted 
          playsInline 
        />
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
              min="1000"
              step="500"
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