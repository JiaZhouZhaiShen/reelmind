import { request } from './base';
import type { AuthResponse, UserInfo } from './client';

export function login(username: string, password: string): Promise<AuthResponse> {
  return request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
}
export function register(username: string, password: string): Promise<AuthResponse> {
  return request('/auth/register', { method: 'POST', body: JSON.stringify({ username, password }) });
}
export function me(): Promise<UserInfo> {
  return request('/auth/me');
}
