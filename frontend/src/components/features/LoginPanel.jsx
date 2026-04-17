import { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { apiFetch } from '../../api/apiClient';

function LoginPanel() {
  const { login } = useAuth();
  
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  async function handleLogin(event) {
    event.preventDefault();

    if (!username.trim() || !password.trim()) {
      setMessage('Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu');
      setError(true);
      return;
    }

    setIsLoading(true);
    setMessage('Đang đăng nhập...');
    setError(false);

    try {
      const response = await apiFetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          username: username.trim(), 
          password 
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || 'Đăng nhập thất bại');
      }

      const data = await response.json();
      
      login(data.data.access_token);
      
      setMessage('Đăng nhập thành công');
      setError(false);

    } catch (err) {
      console.error(err);
      setMessage(err.message || 'Lỗi đăng nhập');
      setError(true);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-hero">
          <h2>Face Attendance</h2>
          <p>Đăng nhập quản trị để truy cập hệ thống điểm danh.</p>
        </div>

        <form className="login-form" onSubmit={handleLogin}>
          <label>
            Tên đăng nhập
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Nhập tài khoản admin"
              autoComplete="username"
              disabled={isLoading}
            />
          </label>

          <label>
            Mật khẩu
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Nhập mật khẩu"
              autoComplete="current-password"
              disabled={isLoading}
            />
          </label>

          <button
            className="btn btn-primary login-submit"
            type="submit"
            disabled={isLoading}
          >
            {isLoading ? 'Đang đăng nhập...' : 'Đăng nhập'}
          </button>
        </form>

        <p className="login-note">
          Phiên đăng nhập chỉ tồn tại trong phiên làm việc hiện tại. Đóng ứng dụng sẽ tự đăng xuất.
        </p>

        {message && (
          <div className={error ? 'message error' : 'message success'}>
            {message}
          </div>
        )}
      </div>
    </div>
  );
}

export default LoginPanel;