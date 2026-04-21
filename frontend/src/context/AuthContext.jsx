import { createContext, useContext, useState, useEffect } from 'react';
import {
  setToken,
  getToken,
  clearToken,
  verifyAuthToken,
  apiLogout,
  bestEffortLogoutOnClose,
} from '../api/apiClient';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function bootstrapAuth() {
      const existingToken = getToken();
      if (!existingToken) {
        if (isMounted) setIsLoading(false);
        return;
      }

      const isValid = await verifyAuthToken();
      if (isMounted) {
        if (isValid) {
          setTokenState(existingToken);
        } else {
          clearToken();
          setTokenState(null);
        }
        setIsLoading(false);
      }
    }

    bootstrapAuth();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
  const handleBeforeUnload = () => {
    // ❌ KHÔNG logout khi reload
    // bestEffortLogoutOnClose(getToken());
  };

  window.addEventListener('beforeunload', handleBeforeUnload);
  return () => {
    window.removeEventListener('beforeunload', handleBeforeUnload);
  };
}, []);

  const login = (newToken) => {
    setToken(newToken);
    setTokenState(newToken);
  };

  const logout = async () => {
    await apiLogout();
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