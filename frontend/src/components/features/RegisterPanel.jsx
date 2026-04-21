import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api/apiClient';

const TARGET_FRAMES = 10;
const BURST_INTERVAL_MS = 220;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function RegisterPanel({ onRegisterSuccess }) {
  const [name, setName] = useState('');
  const [mssv, setMssv] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [isCapturingBurst, setIsCapturingBurst] = useState(false);
  const [captureProgress, setCaptureProgress] = useState(0);
  const [capturedFrames, setCapturedFrames] = useState([]);
  const [stepHint, setStepHint] = useState('');

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const shouldStopCaptureRef = useRef(false);

  useEffect(() => {
    return () => {
      shouldStopCaptureRef.current = true;
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
    };
  }, []);

  function resetCaptureState() {
    setCapturedFrames([]);
    setCaptureProgress(0);
    setStepHint('');
  }

  function stopCamera() {
    shouldStopCaptureRef.current = true;
    setCameraActive(false);
    setIsCapturingBurst(false);
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }

  async function captureFrameBlob() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return null;

    const width = video.videoWidth || 640;
    const height = video.videoHeight || 480;
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, width, height);

    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.86);
    });
  }

  // Mở camera để bắt đầu đăng ký nhanh
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
      shouldStopCaptureRef.current = false;
      setCameraActive(true);
      resetCaptureState();
      setMessage(`Camera đã sẵn sàng. Nhấn "Tự chụp nhanh" để lấy ${TARGET_FRAMES} ảnh liên tiếp.`);
      setError(false);
    } catch (err) {
      setMessage('Không mở được camera. Vui lòng kiểm tra quyền truy cập.');
      setError(true);
    }
  }

  async function captureBurstFrames() {
    if (!cameraActive || isCapturingBurst || isLoading) return;

    setIsCapturingBurst(true);
    setIsLoading(true);
    setError(false);
    resetCaptureState();
    setMessage('Đang tự động chụp ảnh liên tiếp...');

    const frames = [];
    let noFaceWarnings = 0;

    try {
      for (let i = 0; i < TARGET_FRAMES; i += 1) {
        if (shouldStopCaptureRef.current) break;

        setCaptureProgress(i + 1);
        setStepHint(`Đang lấy khung hình ${i + 1}/${TARGET_FRAMES}`);

        const blob = await captureFrameBlob();
        if (!blob) {
          noFaceWarnings += 1;
          await wait(BURST_INTERVAL_MS);
          continue;
        }

        if (i === 0 || i === TARGET_FRAMES - 1 || i % 3 === 0) {
          const previewFormData = new FormData();
          previewFormData.append('file', blob, `preview_${i + 1}.jpg`);
          const previewResponse = await apiFetch('/face/check', {
            method: 'POST',
            body: previewFormData,
          });

          if (!previewResponse.ok) {
            noFaceWarnings += 1;
            await wait(BURST_INTERVAL_MS);
            continue;
          }

          const previewData = await previewResponse.json();
          const faceCount = previewData?.data?.face_count ?? 0;
          if (faceCount < 1) {
            noFaceWarnings += 1;
            await wait(BURST_INTERVAL_MS);
            continue;
          }
        }

        frames.push({
          blob,
          frameNumber: frames.length + 1,
        });

        await wait(BURST_INTERVAL_MS);
      }

      setCapturedFrames(frames);

      if (frames.length < TARGET_FRAMES) {
        setMessage(
          `Đã chụp ${frames.length}/${TARGET_FRAMES} ảnh hợp lệ. ` +
          `Bạn có thể tự chụp lại để đủ dữ liệu tốt hơn.`
        );
        if (noFaceWarnings > 0) {
          setStepHint(`Lưu ý: ${noFaceWarnings} khung hình không thấy mặt rõ.`);
        }
      } else {
        setMessage(`Đã thu đủ ${TARGET_FRAMES} ảnh. Nhấn "Gửi đăng ký" để lưu embedding.`);
      }
    } catch (err) {
      setError(true);
      setMessage('Không thể tự chụp ảnh. Vui lòng thử lại.');
    } finally {
      setIsCapturingBurst(false);
      setIsLoading(false);
    }
  }

  async function submitRegistration() {
    if (capturedFrames.length < TARGET_FRAMES) {
      setMessage(
        `Chưa đủ ảnh (${capturedFrames.length}/${TARGET_FRAMES}). ` +
        'Hãy dùng tính năng tự chụp lại để có đủ dữ liệu.'
      );
      setError(true);
      return;
    }

    setIsLoading(true);
    setError(false);
    setMessage('Đang gửi ảnh đăng ký và trích xuất embedding...');

    try {
      const formData = new FormData();
      formData.append('name', name.trim());
      if (mssv.trim()) formData.append('mssv', mssv.trim());
      // chỉ gửi ảnh đầu tiên
      formData.append('file', capturedFrames[0].blob, 'face.jpg');
      
      capturedFrames.forEach((frame) => {
        formData.append('files', frame.blob, `frame_${frame.frameNumber}.jpg`);
      });

      const res = await apiFetch('/register', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Đăng ký thất bại');
      }

      await res.json();
      setMessage(`Đăng ký thành công: ${name} (${capturedFrames.length}/${TARGET_FRAMES} ảnh)`);
      
      setName('');
      setMssv('');
      resetCaptureState();
      stopCamera();
      onRegisterSuccess?.();

    } catch (err) {
      setMessage(err.message || 'Đăng ký thất bại');
      setError(true);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="panel-grid">
      <section className="panel-card register-card">
        <h2>Đăng ký sinh viên mới</h2>
        <p className="register-subtitle">Tự động chụp liên tiếp để tạo nhiều embedding nhanh và ổn định.</p>

        <label className="register-label">
          Tên sinh viên
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Họ và tên" />
        </label>

        <label className="register-label">
          MSSV (nếu có)
          <input value={mssv} onChange={e => setMssv(e.target.value)} placeholder="Ví dụ: 21520001" />
        </label>

        <div className="button-row register-actions">
          <button 
            onClick={startRegistrationCamera}
            className="btn btn-primary"
            disabled={cameraActive || isLoading}
          >
            Mở camera
          </button>

          <button
            onClick={captureBurstFrames}
            className="btn btn-accent"
            disabled={!cameraActive || isLoading || isCapturingBurst}
          >
            {isCapturingBurst ? 'Đang tự chụp...' : `Tự chụp nhanh (${TARGET_FRAMES} ảnh)`}
          </button>

          <button
            onClick={submitRegistration}
            className="btn btn-primary"
            disabled={isLoading || capturedFrames.length < TARGET_FRAMES}
          >
            Gửi đăng ký
          </button>

          <button
            onClick={() => {
              resetCaptureState();
              setMessage('Đã làm mới bộ ảnh chụp. Bạn có thể tự chụp lại.');
              setError(false);
            }}
            className="btn btn-secondary"
            disabled={!cameraActive || isLoading}
          >
            Chụp lại
          </button>

          <button
            onClick={() => {
              stopCamera();
              resetCaptureState();
              setMessage('Đã tắt camera.');
              setError(false);
            }}
            className="btn btn-danger"
            disabled={!cameraActive || isLoading}
          >
            Tắt camera
          </button>
        </div>

        {cameraActive && (
          <>
            <p className="helper-text">Đã chụp: {capturedFrames.length}/{TARGET_FRAMES}</p>
            <p className="helper-text">Tiến độ phiên hiện tại: {captureProgress}/{TARGET_FRAMES}</p>
            {stepHint && <p className="helper-text">{stepHint}</p>}
          </>
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