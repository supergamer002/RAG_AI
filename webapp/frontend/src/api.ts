const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export function getApiToken(): string {
  try { return localStorage.getItem('rag_api_token') || ''; } catch { return ''; }
}

export function setApiToken(token: string): void {
  try {
    if (token) localStorage.setItem('rag_api_token', token);
    else localStorage.removeItem('rag_api_token');
  } catch { /* storage may be unavailable */ }
}

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getApiToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(apiUrl(path), { ...init, headers });
}

export async function apiJson<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  const text = await response.text();
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!response.ok) {
    const detail = data?.detail || data?.message || text || `HTTP ${response.status}`;
    throw new Error(String(detail));
  }
  return data as T;
}
