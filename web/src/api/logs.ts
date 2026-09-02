import { request } from './base';

export interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  raw: string;
}

export interface LogSource {
  id: string;
  label: string;
  type: 'docker' | 'file';
  status: string;
  has_logs: boolean;
}

export interface LogResult {
  source: string;
  lines: LogEntry[];
  total_lines: number;
  truncated: boolean;
  docker_available: boolean;
  error?: string;
}

export interface SourceListResponse {
  sources: LogSource[];
  error?: string;
}

export interface SearchResultItem {
  timestamp: string;
  level: string;
  message: string;
}

export interface SearchResultGroup {
  source: string;
  label: string;
  matches: SearchResultItem[];
  total_matches: number;
}

export interface SearchResponse {
  query: string;
  results: SearchResultGroup[];
  error?: string;
}

export interface ScanJobInfo {
  id: string;
  status: string;
  progress: number;
  message?: string;
  error?: string;
  created_at: string;
  finished_at?: string;
}
export interface AdminSettingValue {
  key: string;
  value: string;
  value_type: string;
  category: string;
  description: string;
}
export interface SystemStatus {
  gpu: { ai_used: number; total_used: number; total: number; ai_percent: number; total_percent: number }
  models: Record<string, boolean>
}
export interface AdminDashboard {
  total_assets: number;
  total_size_bytes: number;
  total_duration_seconds: number;
  pending_import: number;
  total_users: number;
  running_jobs: number;
  failed_jobs: number;
}
export interface AdminUser {
  id: string;
  username: string;
  role: string;
  created_at?: string;
}
export interface AdminJob {
  id: string;
  job_type: string;
  status: string;
  progress: number;
  message?: string;
  error?: string;
  asset_id?: string;
  library_id?: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
}

export function getLogSources(): Promise<SourceListResponse> {
  return request('/admin/logs/sources');
}

export function getLogs(
  sourceId: string,
  params?: { tail?: number; search?: string; level?: string },
): Promise<LogResult> {
  const qs = new URLSearchParams();
  if (params?.tail !== undefined) qs.set('tail', String(params.tail));
  if (params?.search) qs.set('search', params.search);
  if (params?.level) qs.set('level', params.level);
  const q = qs.toString();
  return request(`/admin/logs/source/${encodeURIComponent(sourceId)}${q ? '?' + q : ''}`);
}

export function searchLogs(
  query: string,
  params?: { sources?: string; tail?: number },
): Promise<SearchResponse> {
  const qs = new URLSearchParams({ q: query });
  if (params?.sources) qs.set('sources', params.sources);
  if (params?.tail !== undefined) qs.set('tail', String(params.tail));
  return request(`/admin/logs/search?${qs}`);
}

export function getStreamUrl(sourceId: string): string {
  const token = localStorage.getItem('reelmind_token');
  const base = (window as any).__API_BASE__ || '/api';
  let url = `${base}/admin/logs/stream/${encodeURIComponent(sourceId)}`;
  if (token) url += `?token=${encodeURIComponent(token)}`;
  return url;
}
