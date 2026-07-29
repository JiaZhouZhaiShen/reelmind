 // In dev mode, use absolute URL to bypass Vite proxy issues in some browsers
 export const BASE = import.meta.env.DEV ? 'http://localhost:2588/api' : '/api';

const TOKEN_KEY = 'reelmind_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}
export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { ...headers, ...(options?.headers as Record<string, string> || {}) },
      ...options,
    });
  } catch (err: unknown) {
    const msg = err instanceof TypeError && err.message === 'Failed to fetch'
      ? '网络连接失败，请检查网络后重试'
      : String(err);
    throw new Error(msg);
  }
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}
