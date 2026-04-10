import { createContext, useContext, useState, useEffect } from 'react';
import { setToken, getToken, clearToken } from '../api/apiClient';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(getToken());
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Khởi tạo token từ localStorage
    setTokenState(getToken());
    setIsLoading(false);
  }, []);

  const login = (newToken) => {
    setToken(newToken);
    setTokenState(newToken);
  };

  const logout = () => {
    clearToken();
    setTokenState(null);
  };

  const value = {
    token,
    isAuthenticated: !!token,
    login,
    logout,
    isLoading
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};