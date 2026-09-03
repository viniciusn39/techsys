import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, clearTokens, getTokens, setActingTenant, setTokens } from "../api/client";
import type { Me } from "../types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
  actAsTenant: (tenantId: number | null) => Promise<void>;
}

const AuthContext = createContext<AuthState>(null as any);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    try {
      setMe(await api.get<Me>("/api/auth/me/"));
    } catch {
      setMe(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      if (getTokens().access) await refreshMe();
      setLoading(false);
    })();
  }, [refreshMe]);

  const login = async (email: string, password: string) => {
    const data = await api.post<{ access: string; refresh: string }>(
      "/api/auth/token/",
      { email, password }
    );
    setTokens(data.access, data.refresh);
    await refreshMe();
  };

  const logout = () => {
    clearTokens();
    setMe(null);
  };

  const actAsTenant = async (tenantId: number | null) => {
    setActingTenant(tenantId ? String(tenantId) : null);
    await refreshMe();
  };

  return (
    <AuthContext.Provider value={{ me, loading, login, logout, refreshMe, actAsTenant }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
