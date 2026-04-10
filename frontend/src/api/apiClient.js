const API_BASE = 'http://127.0.0.1:8000/api';

export function getToken() {
  return localStorage.getItem('fa_token');
}

export function setToken(token) {
  localStorage.setItem('fa_token', token);
}

export function clearToken() {
  localStorage.removeItem('fa_token');
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

// Export cả API_BASE để AttendancePanel dùng
export { API_BASE };