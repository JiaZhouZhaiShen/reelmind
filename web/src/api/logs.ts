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
