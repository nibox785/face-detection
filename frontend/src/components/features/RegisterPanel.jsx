import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api/apiClient';

function RegisterPanel({ onRegisterSuccess }) {
  const [name, setName] = useState('');
  const [mssv, setMssv] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);

  const fileRef = useRef(null);
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

  async function captureAndRegister() {
    if (!cameraActive) return;

    const blob = await new Promise(resolve => {
      canvasRef.current.toBlob(resolve, 'image/jpeg', 0.92);
    });

    if (!blob) return;

    setIsLoading(true);
    const formData = new FormData();
    formData.append('name', name.trim());
    if (mssv.trim()) formData.append('mssv', mssv.trim());   // gửi MSSV
    formData.append('file', blob, 'registration.jpg');

    try {
      const res = await apiFetch('/dataset/register', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error('Đăng ký thất bại');

      const data = await res.json();
      setMessage(`✅ Đăng ký thành công: ${name} (${mssv || 'Không có MSSV'})`);
      
      // Reset
      setName('');
      setMssv('');
      fileRef.current.value = '';
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
            onClick={captureAndRegister}
            className="btn btn-success"
            disabled={isLoading}
          >
            {isLoading ? 'Đang lưu...' : '📸 Chụp & Đăng ký ngay'}
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