const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export type ApiErrorKind = 'network' | 'timeout' | 'http' | 'malformed';

export class ApiError extends Error {
  kind: ApiErrorKind;
  status?: number;
  endpoint: string;

  constructor(
    kind: ApiErrorKind,
    message: string,
    endpoint: string,
    status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.endpoint = endpoint;
  }
}

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

export function formatApiError(error: unknown, operation?: string): string {
  const prefix = operation ? `${operation}: ` : '';
  if (error instanceof ApiError) {
    switch (error.kind) {
      case 'network':
        return `${prefix}backend non raggiungibile (${error.endpoint})`;
      case 'timeout':
        return `${prefix}timeout verso ${error.endpoint}`;
      case 'http':
        if (error.status === 401) return `${prefix}autenticazione richiesta (HTTP 401, ${error.endpoint})`;
        if (error.status === 403) return `${prefix}accesso negato (HTTP 403, ${error.endpoint})`;
        if (error.status && error.status >= 400 && error.status < 500) {
          return `${prefix}errore client HTTP ${error.status} (${error.endpoint}): ${error.message}`;
        }
        if (error.status && error.status >= 500) {
          return `${prefix}errore backend HTTP ${error.status} (${error.endpoint}): ${error.message}`;
        }
        return `${prefix}${error.message} (${error.endpoint})`;
      case 'malformed':
        return `${prefix}risposta non valida dal backend (${error.endpoint})`;
    }
  }
  return `${prefix}${error instanceof Error ? error.message : 'errore sconosciuto'}`;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getApiToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const controller = new AbortController();
  let timeoutId: number | undefined;
  const externalSignal = init.signal;

  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  timeoutId = window.setTimeout(() => controller.abort(), 15000);

  try {
    return await fetch(apiUrl(path), {
      ...init,
      headers,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (externalSignal?.aborted) {
        throw new ApiError('network', 'Richiesta annullata.', path);
      }
      throw new ApiError('timeout', 'Richiesta scaduta.', path);
    }
    throw new ApiError('network', error instanceof Error ? error.message : 'Errore di rete.', path);
  } finally {
    if (timeoutId !== undefined) window.clearTimeout(timeoutId);
  }
}

export async function apiJson<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  const text = await response.text();
  let data: any = null;

  if (text.trim()) {
    try {
      data = JSON.parse(text);
    } catch {
      if (response.ok) {
        throw new ApiError('malformed', 'Il server ha restituito una risposta non JSON.', path, response.status);
      }
    }
  }

  if (!response.ok) {
    const detail = data?.detail || data?.message || text || `HTTP ${response.status}`;
    throw new ApiError('http', String(detail), path, response.status);
  }

  return data as T;
}
