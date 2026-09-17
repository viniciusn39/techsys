import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, clearTokens, getActingMap, getTokens, setActingMap, setActingTenant, setTokens } from "../api/client";
import type { Me } from "../types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
  actAsTenant: (tenantId: number | null) => Promise<void>;
  /** Planejamento em uso; null = o padrão da empresa. Trocar remonta as telas. */
  mapId: number | null;
  selectMap: (mapId: number | null) => void;
}

const AuthContext = createContext<AuthState>(null as any);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [mapId, setMapId] = useState<number | null>(getActingMap() ? Number(getActingMap()) : null);

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
    setMapId(null);
    setMe(null);
  };

  const actAsTenant = async (tenantId: number | null) => {
    setActingTenant(tenantId ? String(tenantId) : null);
    setMapId(null);
    await refreshMe();
  };

  const selectMap = (id: number | null) => {
    setActingMap(id ? String(id) : null);
    setMapId(id);
  };

  return (
    <AuthContext.Provider value={{ me, loading, login, logout, refreshMe, actAsTenant, mapId, selectMap }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
