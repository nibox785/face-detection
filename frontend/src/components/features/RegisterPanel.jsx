import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../api/apiClient';

const REGISTRATION_STEPS = [
  'Nhìn thẳng vào camera',
  'Xoay nhẹ sang trái',
  'Xoay nhẹ sang phải',
  'Ngẩng mặt lên',
  'Cúi mặt xuống',
  'Nghiêng đầu sang trái',
  'Nghiêng đầu sang phải',
  'Tiến gần camera một chút',
  'Lùi xa camera một chút',
  'Nhìn thẳng và giữ ổn định',
];

function RegisterPanel({ onRegisterSuccess }) {
  const [name, setName] = useState('');
  const [mssv, setMssv] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [capturedFrames, setCapturedFrames] = useState([]);
  const [stepHint, setStepHint] = useState('');

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
      setStepIndex(0);
      setCapturedFrames([]);
      setStepHint('');
      setMessage(`✅ Camera đã mở. Bước 1/${REGISTRATION_STEPS.length}: ${REGISTRATION_STEPS[0]}`);
      setError(false);
    } catch (err) {
      setMessage('❌ Không mở được camera. Vui lòng kiểm tra quyền truy cập.');
      setError(true);
    }
  }

  async function captureCurrentStep() {
    if (!cameraActive || !videoRef.current || !canvasRef.current) return;

    if (stepIndex >= REGISTRATION_STEPS.length) {
      setMessage('Đã chụp đủ ảnh. Hãy gửi đăng ký.');
      setError(false);
      return;
    }

    setIsLoading(true);
    setError(false);

    const ctx = canvasRef.current.getContext('2d');
    canvasRef.current.width = videoRef.current.videoWidth;
    canvasRef.current.height = videoRef.current.videoHeight;
    ctx.drawImage(videoRef.current, 0, 0);

    const blob = await new Promise(resolve => {
      canvasRef.current.toBlob(resolve, 'image/jpeg', 0.85);
    });

    if (!blob) {
      setMessage('❌ Không thể chụp ảnh ở bước hiện tại. Vui lòng thử lại.');
      setError(true);
      setIsLoading(false);
      return;
    }

    const previewFormData = new FormData();
    previewFormData.append('file', blob, `preview_step_${stepIndex + 1}.jpg`);

    const previewResponse = await apiFetch('/face/check', {
      method: 'POST',
      body: previewFormData,
    });

    if (!previewResponse.ok) {
      const errorData = await previewResponse.json().catch(() => ({}));
      setMessage(`❌ ${errorData.detail || 'Không kiểm tra được khuôn mặt. Hãy căn chỉnh lại ảnh.'}`);
      setError(true);
      setIsLoading(false);
      return;
    }

    const previewData = await previewResponse.json();
    const faceCount = previewData?.data?.face_count ?? 0;

    if (faceCount < 1) {
      setMessage(`❌ Bước ${stepIndex + 1}: không phát hiện được khuôn mặt. Hãy giữ mặt rõ hơn rồi chụp lại.`);
      setError(true);
      setIsLoading(false);
      return;
    }

    const bestFace = previewData.data.faces?.[0];
    const qualityScore = bestFace?.quality_score ?? 0;
    setStepHint(`Đã phát hiện mặt, quality=${qualityScore.toFixed(2)}`);

    const currentStepNumber = stepIndex + 1;
    const currentStepName = REGISTRATION_STEPS[stepIndex];

    setCapturedFrames(prev => [
      ...prev,
      {
        blob,
        stepName: currentStepName,
        stepNumber: currentStepNumber,
      },
    ]);

    if (currentStepNumber >= REGISTRATION_STEPS.length) {
      setStepIndex(REGISTRATION_STEPS.length);
      setMessage(`✅ Đã chụp đủ ${REGISTRATION_STEPS.length} bước. Nhấn "Gửi đăng ký" để trích xuất đặc trưng khuôn mặt.`);
    } else {
      const nextIndex = currentStepNumber;
      setStepIndex(nextIndex);
      setMessage(
        `✅ Đã chụp xong bước ${currentStepNumber}/${REGISTRATION_STEPS.length}. ` +
        `Tiếp theo: ${REGISTRATION_STEPS[nextIndex]}`
      );
    }

    setIsLoading(false);
  }

  async function submitRegistration() {
    if (capturedFrames.length < REGISTRATION_STEPS.length) {
      setMessage(
        `❌ Chưa đủ ảnh (${capturedFrames.length}/${REGISTRATION_STEPS.length}). ` +
        'Hãy chụp đủ các góc mặt trước khi gửi.'
      );
      setError(true);
      return;
    }

    setIsLoading(true);
    setError(false);
    setMessage('⏳ Đang gửi ảnh đăng ký và trích xuất đặc trưng khuôn mặt...');

    // Send all frames to backend
    try {
      const formData = new FormData();
      formData.append('name', name.trim());
      if (mssv.trim()) formData.append('mssv', mssv.trim());
      
      capturedFrames.forEach((frame) => {
        const safeStep = frame.stepName
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '_')
          .replace(/^_+|_+$/g, '');
        formData.append('files', frame.blob, `step_${frame.stepNumber}_${safeStep}.jpg`);
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
      setMessage(`✅ Đăng ký thành công: ${name} (${capturedFrames.length}/${REGISTRATION_STEPS.length} góc mặt)`);
      
      // Reset + close camera
      setName('');
      setMssv('');
      setStepIndex(0);
      setCapturedFrames([]);
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
          <>
            <p className="helper-text">
              {stepIndex < REGISTRATION_STEPS.length
                ? `Bước hiện tại: ${stepIndex + 1}/${REGISTRATION_STEPS.length} - ${REGISTRATION_STEPS[stepIndex]}`
                : `Đã hoàn tất ${REGISTRATION_STEPS.length}/${REGISTRATION_STEPS.length} bước chụp`}
            </p>
            <p className="helper-text">
              Đã chụp: {capturedFrames.length}/{REGISTRATION_STEPS.length}
            </p>
            {stepHint && <p className="helper-text">{stepHint}</p>}
            <div className="button-row">
              <button 
                onClick={captureCurrentStep}
                className="btn btn-success"
                disabled={isLoading || stepIndex >= REGISTRATION_STEPS.length}
              >
                {isLoading ? 'Đang chụp...' : '📸 Chụp bước hiện tại'}
              </button>
              <button
                onClick={submitRegistration}
                className="btn btn-primary"
                disabled={isLoading || capturedFrames.length < REGISTRATION_STEPS.length}
              >
                Gửi đăng ký
              </button>
            </div>
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