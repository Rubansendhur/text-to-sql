import { createContext, useContext, useState, useEffect } from 'react';
import { API_BASE } from '../lib/api.js';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const bootstrapAuth = async () => {
      // Validate any stored token before considering the user logged in.
      const token = localStorage.getItem('access_token');
      const role = localStorage.getItem('role');
      const username = localStorage.getItem('username');
      const departmentCode = localStorage.getItem('department_code');

      if (!token || !role || !username) {
        setLoading(false);
        return;
      }

      try {
        const res = await fetch(`${API_BASE}/api/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!res.ok) {
          throw new Error('Invalid token');
        }

        const profile = await res.json();
        setUser({
          token,
          role: profile.role || role,
          username: profile.username || username,
          department_code: profile.department_code ?? departmentCode,
        });
      } catch {
        localStorage.removeItem('access_token');
        localStorage.removeItem('role');
        localStorage.removeItem('username');
        localStorage.removeItem('department_code');
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    bootstrapAuth();
  }, []);

  const login = (userData) => {
    localStorage.setItem('access_token', userData.access_token);
    localStorage.setItem('role', userData.role);
    localStorage.setItem('username', userData.username);
    localStorage.setItem('department_code', userData.department_code || '');
    setUser({
      token: userData.access_token,
      role: userData.role,
      username: userData.username,
      department_code: userData.department_code,
    });
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('role');
    localStorage.removeItem('username');
    localStorage.removeItem('department_code');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
        {!loading && children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
