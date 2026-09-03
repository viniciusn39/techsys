const ACCESS_KEY = "ts_access";
const REFRESH_KEY = "ts_refresh";
const TENANT_KEY = "ts_tenant";

export function getTokens() {
  return {
    access: localStorage.getItem(ACCESS_KEY),
    refresh: localStorage.getItem(REFRESH_KEY),
  };
}

export function setTokens(access: string, refresh?: string) {
  localStorage.setItem(ACCESS_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(TENANT_KEY);
}

export function getActingTenant(): string | null {
  return localStorage.getItem(TENANT_KEY);
}

export function setActingTenant(id: string | null) {
  if (id) localStorage.setItem(TENANT_KEY, id);
  else localStorage.removeItem(TENANT_KEY);
}

export class ApiError extends Error {
  status: number;
  data: any;
  constructor(status: number, data: any) {
    super(typeof data === "string" ? data : data?.detail || `Erro ${status}`);
    this.status = status;
    this.data = data;
  }
}

async function refreshAccess(): Promise<boolean> {
  const { refresh } = getTokens();
  if (!refresh) return false;
  const resp = await fetch("/api/auth/token/refresh/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!resp.ok) return false;
  const data = await resp.json();
  setTokens(data.access);
  return true;
}

async function request<T>(method: string, url: string, body?: any, retry = true): Promise<T> {
  const { access } = getTokens();
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (access) headers["Authorization"] = `Bearer ${access}`;
  const tenant = getActingTenant();
  if (tenant) headers["X-Tenant-Id"] = tenant;

  const resp = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (resp.status === 401 && retry && (await refreshAccess())) {
    return request<T>(method, url, body, false);
  }
  if (resp.status === 204) return undefined as T;
  const data = await resp.json().catch(() => null);
  if (!resp.ok) throw new ApiError(resp.status, data);
  return data as T;
}

export const api = {
  get: <T = any>(url: string) => request<T>("GET", url),
  post: <T = any>(url: string, body?: any) => request<T>("POST", url, body),
  put: <T = any>(url: string, body?: any) => request<T>("PUT", url, body),
  patch: <T = any>(url: string, body?: any) => request<T>("PATCH", url, body),
  del: <T = any>(url: string) => request<T>("DELETE", url),
};
