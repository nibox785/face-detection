import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api/apiClient';

function RegisterPanel({ onRegisterSuccess }) {
  const [name, setName] = useState('');
  const [mssv, setMssv] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => {
    return () => {
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
    };
  }, []);

  // Mở camera khi nhấn "Đăng ký bằng Camera"
  async function startRegistrationCamera() {
    if (!name.trim()) {
      setMessage('Vui lòng nhập tên sinh viên');
      setError(true);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { facingMode: "user" } 
      });
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      streamRef.current = stream;
      setCameraActive(true);
      setMessage('✅ Camera đã mở. Hãy nhìn thẳng vào camera...');
      setError(false);
    } catch (err) {
      setMessage('❌ Không mở được camera. Vui lòng kiểm tra quyền truy cập.');
      setError(true);
    }
  }

  async function captureMultipleFrames() {
    if (!cameraActive || !videoRef.current || !canvasRef.current) return;

    setIsLoading(true);
    setMessage('📸 Quét khuôn mặt từ các góc khác nhau...');
    setError(false);

    const frames = [];
    const ctx = canvasRef.current.getContext('2d');
    const frameCount = 40; // Capture 40 frames
    const intervalMs = 100; // Every 100ms = 10 fps

    for (let i = 0; i < frameCount; i++) {
      if (!videoRef.current || !videoRef.current.readyState) break;

      canvasRef.current.width = videoRef.current.videoWidth;
      canvasRef.current.height = videoRef.current.videoHeight;
      ctx.drawImage(videoRef.current, 0, 0);

      const blob = await new Promise(resolve => {
        canvasRef.current.toBlob(resolve, 'image/jpeg', 0.85);
      });

      if (blob) frames.push(blob);
      
      // Show progress
      setMessage(`📸 Quét khuôn mặt ${i + 1}/${frameCount}...`);
      
      // Wait before next capture
      await new Promise(r => setTimeout(r, intervalMs));
    }

    if (frames.length === 0) {
      setMessage('❌ Không thể chụp ảnh. Vui lòng thử lại.');
      setError(true);
      setIsLoading(false);
      return;
    }

    // Send all frames to backend
    try {
      const formData = new FormData();
      formData.append('name', name.trim());
      if (mssv.trim()) formData.append('mssv', mssv.trim());
      
      // Append all frames
      frames.forEach((blob, idx) => {
        formData.append('files', blob, `frame_${idx}.jpg`);
      });

      const res = await apiFetch('/dataset/register-multiple', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Đăng ký thất bại');
      }

      const data = await res.json();
      setMessage(`✅ Đăng ký thành công: ${name} (${frames.length} ảnh)`);
      
      // Reset + close camera
      setName('');
      setMssv('');
      setCameraActive(false);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
        streamRef.current = null;
      }
      onRegisterSuccess?.();

    } catch (err) {
      setMessage(`❌ ${err.message}`);
      setError(true);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="panel-grid">
      <section className="panel-card">
        <h2>📝 Đăng ký sinh viên mới</h2>

        <label>
          Tên sinh viên
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Họ và tên" />
        </label>

        <label>
          MSSV (nếu có)
          <input value={mssv} onChange={e => setMssv(e.target.value)} placeholder="Ví dụ: 21520001" />
        </label>

        <div className="button-row">
          <button 
            onClick={startRegistrationCamera}
            className="btn btn-primary"
            disabled={cameraActive || isLoading}
          >
            📷 Đăng ký bằng Camera
          </button>
        </div>

        {cameraActive && (
          <button 
            onClick={captureMultipleFrames}
            className="btn btn-success"
            disabled={isLoading}
          >
            {isLoading ? 'Đang quét...' : '📸 Bắt đầu quét khuôn mặt'}
          </button>
        )}

        {message && <div className={error ? 'message error' : 'message success'}>{message}</div>}
      </section>

      <section className="panel-card camera-card">
        <h3>Camera Preview</h3>
        <video ref={videoRef} className="camera-preview" muted playsInline />
        <canvas ref={canvasRef} hidden />
      </section>
    </div>
  );
}

export default RegisterPanel;