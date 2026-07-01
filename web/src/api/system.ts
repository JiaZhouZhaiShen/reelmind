import { request } from './base';
import type { SystemStats, AdminSettingValue, AdminDashboard, SystemStatus, AdminUser, AdminJob, MetadataFieldListResponse } from './client';

export function ping(): Promise<{ status: string; app: string; version: string }> {
  return request('/ping');
}
export function stats(): Promise<SystemStats> {
  return request('/system/stats');
}
export function health(): Promise<{ status: string; free_space_gb: number }> {
  return request('/system/health');
}

// Admin
export function getAdminSettings(): Promise<Record<string, AdminSettingValue>> {
  return request('/admin/settings');
}
export function updateAdminSettings(settings: Record<string, string>): Promise<{ status: string; updated: string[] }> {
  return request('/admin/settings', { method: 'PUT', body: JSON.stringify(settings) });
}
export function getAIStats(): Promise<{
  videos_processed: number;
  total_scenes: number;
  total_subtitles: number;
  total_tags: number;
  total_ocr_texts: number;
  total_frames: number;
  speakers_found: number;
}> {
  return request('/admin/ai/stats');
}

export function getAdminDashboard(): Promise<AdminDashboard> {
  return request('/admin/dashboard');
}
export function getSystemStatus(): Promise<SystemStatus> {
  return request('/admin/system-status');
}
export function listAdminUsers(): Promise<AdminUser[]> {
  return request('/admin/users');
}
export function createAdminUser(data: { username: string; password: string; role?: string }): Promise<AdminUser> {
  return request('/admin/users', { method: 'POST', body: JSON.stringify(data) });
}
export function updateAdminUser(userId: string, data: { role?: string; password?: string }): Promise<{ status: string }> {
  return request(`/admin/users/${userId}`, { method: 'PATCH', body: JSON.stringify(data) });
}
export function cleanupAdminJobs(): Promise<{ deleted_old: number; marked_stale: number }> {
  return request('/admin/jobs/cleanup', { method: 'POST' });
}
export function deleteAdminUser(userId: string): Promise<{ status: string }> {
  return request(`/admin/users/${userId}`, { method: 'DELETE' });
}
export function listAdminJobs(statusFilter?: string, limit = 50): Promise<AdminJob[]> {
  const params = new URLSearchParams();
  if (statusFilter) params.set('status_filter', statusFilter);
  params.set('limit', String(limit));
  return request(`/admin/jobs?${params}`);
}
export function retryAdminJob(jobId: string): Promise<{ status: string }> {
  return request(`/admin/jobs/${jobId}/retry`, { method: 'POST' });
}
export function cancelAdminJob(jobId: string): Promise<{ status: string }> {
  return request(`/admin/jobs/${jobId}/cancel`, { method: 'POST' });
}
export function listLogFiles(): Promise<{ directory: string; files: { name: string; size_bytes: number; modified_at: number }[] }> {
  return request('/admin/logs');
}
export function viewLogFile(filename: string, tail = 200): Promise<{ filename: string; lines?: string[]; content?: string; truncated: boolean; total_lines?: number; total_bytes?: number }> {
  return request(`/admin/logs/${encodeURIComponent(filename)}?tail=${tail}`);
}
export function deleteLogFile(filename: string): Promise<{ status: string; message: string }> {
  return request(`/admin/logs/${encodeURIComponent(filename)}`, { method: 'DELETE' });
}
export function clearAllLogs(): Promise<{ status: string; message: string; deleted?: string[] }> {
  return request('/admin/logs', { method: 'DELETE' });
}
export function restartServer(): Promise<{ status: string; message: string }> {
  return request('/admin/restart', { method: 'POST' });
}
export function updateEnvConfig(): Promise<{ status: string; message: string }> {
  return request('/admin/update-env-config', { method: 'POST' });
}
export function getMetadataFieldDefinitions(): Promise<MetadataFieldListResponse> {
  return request('/admin/metadata-fields');
}
