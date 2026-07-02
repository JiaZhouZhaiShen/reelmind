import { request } from './base';
import type { Library, Asset, SearchResult } from './client';

// ── Libraries ──
export function listLibraries(): Promise<Library[]> {
  return request('/libraries');
}
export function getLibrary(id: string): Promise<Library> {
  return request(`/libraries/${id}`);
}
export function createLibrary(data: { name: string; description?: string; import_mode?: string; paths?: string[] }): Promise<Library> {
  return request('/libraries', { method: 'POST', body: JSON.stringify(data) });
}
export function updateLibrary(id: string, data: Partial<Library>): Promise<Library> {
  return request(`/libraries/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}
export function deleteLibrary(id: string): Promise<{ status: string }> {
  return request(`/libraries/${id}`, { method: 'DELETE' });
}
export function scanLibrary(id: string): Promise<{ status: string; library_id: string; scan_job_id: string }> {
  return request(`/scan/${id}`, { method: "POST" });
}
export function scanPause(id: string): Promise<{ status: string; paused_jobs: number; library_id: string }> {
  return request(`/scan/${id}/pause`, { method: "POST" });
}
export function scanResume(id: string): Promise<{ status: string; library_id: string; scan_job_id: string }> {
  return request(`/scan/${id}/resume`, { method: "POST" });
}
export function addLibraryPath(id: string, path: string): Promise<{ status: string; path_id: string }> {
  return request(`/libraries/${id}/paths`, { method: 'POST', body: JSON.stringify({ path, is_network: false }) });
}
export function removeLibraryPath(libId: string, pathId: string): Promise<{ status: string }> {
  return request(`/libraries/${libId}/paths/${pathId}`, { method: 'DELETE' });
}
export function getLibraryScanStatus(libId: string): Promise<{ library_id: string; pending_import: number; recent_jobs: Array<any> }> {
  return request(`/scan/${libId}/status`);
}

// ── Assets ──
export function listAssets(libraryId?: string, page = 1, pageSize = 5000, sortBy = 'media_date', sortOrder = 'asc', isFavorite?: boolean, aiFilter?: string, orientationFilter?: string): Promise<{ items: Asset[]; total: number }> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort_by: sortBy, sort_order: sortOrder });
  if (libraryId) params.set('library_id', libraryId);
  if (!libraryId) params.set('include_archived', 'false');
  if (isFavorite !== undefined) params.set('is_favorite', String(isFavorite));
  if (aiFilter && aiFilter !== 'all') params.set('ai_filter', aiFilter);
  if (orientationFilter && orientationFilter !== 'all') params.set('orientation_filter', orientationFilter);
  return request(`/assets?${params}`);
}
export function listArchivedAssets(libraryId?: string): Promise<{ items: Asset[]; total: number }> {
  const params = new URLSearchParams({ include_archived: 'true' });
  if (libraryId) params.set('library_id', libraryId);
  return request(`/assets?${params}`);
}
export function getAsset(id: string): Promise<Asset> {
  return request(`/assets/${id}`);
}
export function updateAsset(id: string, data: Partial<Asset>): Promise<Asset> {
  return request(`/assets/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}
export function deleteAsset(id: string): Promise<{ status: string }> {
  return request(`/assets/${id}`, { method: 'DELETE' });
}
export function reimportAsset(id: string): Promise<{ status: string }> {
  return request(`/assets/${id}/reimport`, { method: 'POST' });
}

// ── Transcript & Segments ──
export function getTranscript(id: string): Promise<Array<{ start: number; end: number; text: string; language: string }>> {
  return request(`/assets/${id}/transcript`);
}
export function getSegments(id: string): Promise<Array<{ id: string; start_time: number; end_time: number; thumbnail_path?: string; description?: string; scene_label?: string; source: string }>> {
  return request(`/assets/${id}/segments`);
}

export function batchUpdateAssets(assetIds: string[], updates: Record<string, unknown>): Promise<{ status: string; updated: number }> {
  return request('/assets/batch/update', { method: 'POST', body: JSON.stringify({ asset_ids: assetIds, updates }) });
}
export function batchDeleteAssets(assetIds: string[]): Promise<{ status: string; deleted: number }> {
  return request('/assets/batch/delete', { method: 'POST', body: JSON.stringify({ asset_ids: assetIds }) });
}
export function batchTagAssets(assetIds: string[], tagIds: string[], action: 'add' | 'remove'): Promise<{ status: string; affected: number }> {
  return request('/assets/batch/tags', { method: 'POST', body: JSON.stringify({ asset_ids: assetIds, tag_ids: tagIds, action }) });
}

// ── Search ──
export function smartSearch(params: { q?: string; library_id?: string; tags?: string; min_duration?: number; max_duration?: number; has_audio?: boolean; sort_by?: string; sort_order?: string; page?: number; page_size?: number; include_archived?: boolean }): Promise<{ results: SearchResult[]; total: number }> {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') sp.set(k, String(v)); });
  if (!sp.has('include_archived')) sp.set('include_archived', 'false');
  return request(`/search/smart?${sp}`);
}

// ── Preview URLs ──
export function thumbnailUrl(id: string): string {
  return `/api/preview/thumbnail/${id}`;
}
export function proxyUrl(id: string): string {
  return `/api/preview/proxy/${id}`;
}
export function sourceUrl(id: string): string {
  return `/api/preview/source/${id}`;
}
export function segmentThumbnailUrl(segId: string): string {
  return `/api/preview/segment-thumbnail/${segId}`;
}
export function sceneThumbnailUrl(sceneId: string): string {
  return `/api/preview/scene-thumbnail/${sceneId}`;
}
export function downloadUrl(id: string): string {
  return `/api/preview/download/${id}`;
}
export function webvttUrl(id: string): string {
  return `/api/preview/webvtt/${id}`;
}

// ── Download Helpers ──
export function downloadAsset(id: string): void {
  const a = document.createElement('a');
  a.href = downloadUrl(id);
  a.download = '';
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
export function batchResetAssetAI(assetIds: string[]): Promise<{ status: string }> {
  return request('/assets/batch/reset-ai', { method: 'POST', body: JSON.stringify({ asset_ids: assetIds }) });
}

export function getProcessedAssets(): Promise<{ items: Asset[]; total: number }> {
  return request('/assets/processed');
}

export function downloadSelectedAssets(assetIds: string[]): void {
  assetIds.forEach((id, i) => setTimeout(() => downloadAsset(id), 500 * i));
}

// ── Single Asset AI Operations (via Pipeline) ──

export function transcribeAsset(id: string): Promise<{ status: string }> {
  return request(`/assets/${id}/transcribe`, { method: 'POST' });
}

export function generateSceneThumbnails(id: string): Promise<{ status: string }> {
  return request(`/assets/${id}/generate-scenes`, { method: 'POST' });
}

// ── Timeline ──
export function timelineYears(libraryId?: string): Promise<Array<{ year: number; count: number }>> {
  const params = new URLSearchParams();
  if (libraryId) params.set('library_id', libraryId);
  const qs = params.toString();
  return request(`/assets/timeline/years${qs ? `?${qs}` : ''}`);
}
export function timelineMonths(year: number, libraryId?: string): Promise<Array<{ month: number; count: number }>> {
  const params = new URLSearchParams({ year: String(year) });
  if (libraryId) params.set('library_id', libraryId);
  return request(`/assets/timeline/months?${params}`);
}
export function timelineDays(year: number, month: number, libraryId?: string): Promise<Array<{ day: number; count: number }>> {
  const params = new URLSearchParams({ year: String(year), month: String(month) });
  if (libraryId) params.set('library_id', libraryId);
  return request(`/assets/timeline/days?${params}`);
}
export function timelineAssets(year: number, month: number, day: number, libraryId?: string): Promise<Asset[]> {
  const params = new URLSearchParams({ year: String(year), month: String(month), day: String(day) });
  if (libraryId) params.set('library_id', libraryId);
  return request(`/assets/timeline/assets?${params}`);
}
export function timelineDaysByYear(year: number, libraryId?: string): Promise<Array<{ month: number; day: number; count: number }>> {
  const params = new URLSearchParams({ year: String(year) });
  if (libraryId) params.set('library_id', libraryId);
  return request(`/assets/timeline/days-by-year?${params}`);
}

// ── Directory Browsing ──
export function directoryTree(libraryId?: string): Promise<Array<{ name: string; depth: number; children: Array<unknown> }>> {
  const params = new URLSearchParams();
  if (libraryId) params.set('library_id', libraryId);
  const qs = params.toString();
  return request(`/assets/directory-tree${qs ? `?${qs}` : ''}`);
}
export function browsePathDirectories(path: string, libraryId?: string): Promise<string[]> {
  const params = new URLSearchParams({ path });
  if (libraryId) params.set('library_id', libraryId);
  return request(`/assets/browse-path/directories?${params}`);
}
export function browsePath(path: string, libraryId?: string): Promise<Asset[]> {
  const params = new URLSearchParams({ path });
  if (libraryId) params.set('library_id', libraryId);
  return request(`/assets/browse-path?${params}`);
}
export function browsePathPaginated(path: string, libraryId?: string, page = 1, pageSize = 80, sortBy = 'media_date', sortOrder = 'asc'): Promise<{ items: Asset[]; total: number }> {
  const params = new URLSearchParams({ path, page: String(page), page_size: String(pageSize), sort_by: sortBy, sort_order: sortOrder });
  if (libraryId) params.set('library_id', libraryId);
  return request(`/assets/browse-path?${params}`);
}
// ── Auto-Scan Settings ──
export function getScanSettings(): Promise<{ scan_interval_seconds: number }> {
  return request('/system/scan-settings');
}
export function setScanSettings(data: { scan_interval_seconds: number }): Promise<{ status: string }> {
  return request('/system/scan-settings', { method: 'PUT', body: JSON.stringify(data) });
}

// ── Thumbnails ──
export function repairThumbnails(): Promise<{ status: string; message: string; repaired: number; failed: number }> {
  return request('/assets/repair-thumbnails', { method: 'POST' });
}
