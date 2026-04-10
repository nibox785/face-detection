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
  const headers = {
    ...(options.headers || {}),
    ...authHeaders(),
  };
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  });
  return response;
}

export default { API_BASE, getToken, setToken, clearToken, authHeaders, apiFetch };
