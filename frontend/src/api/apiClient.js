const API_BASE = 'http://127.0.0.1:8000/api';
const TOKEN_KEY = 'fa_token';

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  // Session-only token: đóng app/tab sẽ mất token, tránh tự đăng nhập lại.
  sessionStorage.setItem(TOKEN_KEY, token);
  localStorage.removeItem(TOKEN_KEY);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
}

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiFetch(url, options = {}) {
  // Không ghi đè Content-Type khi gửi FormData (browser sẽ tự set)
  const isFormData = options.body instanceof FormData;
  
  const headers = {
    ...(options.headers || {}),
    ...authHeaders(),
  };

  // Xóa Content-Type khi gửi FormData vì browser sẽ tự set
  if (isFormData && headers['Content-Type']) {
    delete headers['Content-Type'];
  }

  try {
    const response = await fetch(`${API_BASE}${url}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      clearToken();
      window.location.reload();
      throw new Error('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
    }

    return response;
  } catch (error) {
    console.error('API Fetch Error:', {
      url: `${API_BASE}${url}`,
      message: error.message,
      stack: error.stack
    });
    throw new Error(error.message || 'Lỗi kết nối đến server');
  }
}

export async function verifyAuthToken() {
  const token = getToken();
  if (!token) return false;

  try {
    const response = await apiFetch('/auth/verify', { method: 'GET' });
    return response.ok;
  } catch (_) {
    return false;
  }
}

export async function apiLogout() {
  try {
    await apiFetch('/logout', { method: 'POST' });
  } catch (_) {
    // Không chặn UX nếu network/server không sẵn sàng.
  } finally {
    clearToken();
  }
}

export function bestEffortLogoutOnClose(token) {
  if (!token) {
    clearToken();
    return;
  }

  try {
    fetch(`${API_BASE}/logout`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      keepalive: true,
    });
  } catch (_) {
    // Bỏ qua lỗi khi đóng tab.
  } finally {
    clearToken();
  }
}

// Export cả API_BASE để AttendancePanel dùng
export { API_BASE };