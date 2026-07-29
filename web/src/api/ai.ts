import { BASE, request } from './base';

/* ── AI 专用 request（自动拼接 /ai 前缀） ── */
function aiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  return request<T>(`/ai${path}`, options);
}

// ── AI Pipeline Config ──




// ── Pipeline Execution ──


    export function getPendingAssetCount(engines?: string[], max_file_size_mb?: number, max_duration_minutes?: number) {
      const params = new URLSearchParams();
      if (engines?.length) params.set("engines", engines.join(","));
      if (max_file_size_mb) params.set("max_file_size_mb", String(max_file_size_mb));
      if (max_duration_minutes) params.set("max_duration_minutes", String(max_duration_minutes));
      const qs = params.toString();
      return aiRequest<any>(`/pending-count${qs ? `?${qs}` : ""}`);
    }

export function getScanStatusAI() {
  return aiRequest<{
    status: string;
    paused?: boolean;
    total?: number;
    completed?: number;
    failed?: number;
    skipped?: number;
    overall_progress?: number;
    current_progress?: number;
    current_index?: number;
    current_stage?: string;
    current_video?: { file_name: string } | null;
    message?: string;
    model_progress?: Record<string, number>;
    videos?: Array<{ file_name: string; status: string }>;
  }>('/scan-status');
}

export function scanLibraryAI() {
  return aiRequest<{ status: string; message: string }>('/scan-library', { method: 'POST' });
}

export function scanPauseAI() {
  return aiRequest<{ status: string; message: string }>('/scan-pause', { method: 'POST' });
}

export function scanResumeAI() {
  return aiRequest<{ status: string; message: string }>('/scan-resume', { method: 'POST' });
}

// ── Models ──

export function getAIModelStatus() {
  return aiRequest<{ models: Record<string, boolean>; gpu: { used: number; total: number; percent: number } }>(
    '/models/status',
  );
}

export function loadAIModel(modelName: string) {
  return aiRequest<{ status: string; model: string; message?: string }>(`/models/load/${modelName}`, {
    method: 'POST',
  });
}

export function unloadAIModel(modelName: string) {
  return aiRequest<{ status: string; model: string }>(`/models/unload/${modelName}`, { method: 'POST' });
}

export function getHFTokenStatus() {
  return aiRequest<{ set: boolean }>('/models/token');
}

export function setHFToken(token: string) {
  return aiRequest<{ status: string; set: boolean }>('/models/token', {
    method: 'POST',
    body: JSON.stringify({ token }),
  });
}

// ── SSE / Progress URLs ──

export function progressUrl(videoId: string) {
  return `${BASE}/ai/progress/${videoId}`;
}

export function scanEventsUrl() {
  return `${BASE}/ai/scan-events`;
}

// ── Auto-Run ──

export function getAutoRunStatus() {
  return aiRequest<any>('/auto-run/status');
}

// ── Cancel / Reset ──

export function cancelAIPipeline(videoId: string) {
  return aiRequest<{ status: string; task_id: string }>(`/process/${videoId}/cancel`, { method: 'POST' });
}



export function resetAssetAI(id: string) {
  return aiRequest<{ status: string; video_id: string }>('/reset-asset/' + id, { method: 'POST' });
}

export function batchResetAssetAI(assetIds: string[]) {
  return aiRequest<{ status: string; total: number; reset_count: number; failed_count: number; failed_ids?: string[] }>(
    '/batch-reset-assets',
    { method: 'POST', body: JSON.stringify({ asset_ids: assetIds }) },
  );
}

// ── Stats ──

export function getAIStats() {
  return aiRequest<{
    videos_processed: number;
    total_scenes: number;
    total_subtitles: number;
    total_tags: number;
    total_ocr_texts: number;
    total_frames: number;
    speakers_found: number;
  }>('/stats');
}

// ── AI Results (SQLite reads proxied through server) ──

export function processAI(videoId: string, videoPath: string) {
  return aiRequest('/process', {
    method: 'POST',
    body: JSON.stringify({ video_id: videoId, video_path: videoPath }),
  });
}

export function getAIStatus(videoId: string) {
  return aiRequest('/status/' + videoId);
}

export function getAISubtitles(videoId: string) {
  return aiRequest('/subtitles/' + videoId);
}

export function getAIScenes(videoId: string) {
  return aiRequest('/scenes/' + videoId);
}

export function getAIFrames(videoId: string) {
  return aiRequest('/frames/' + videoId);
}

export function getAISpeakers(videoId: string) {
  return aiRequest('/speakers/' + videoId);
}

export function getAITags(videoId: string) {
  return aiRequest('/tags/' + videoId);
}


// ── P4: Three Independent Pipeline Configs ──

export function getManualPipelineConfig() {
  return aiRequest<{ config: Record<string, any> }>('/pipeline/manual/config')
}

export function saveManualPipelineConfig(config: Record<string, any>) {
  return aiRequest<{ status: string }>('/pipeline/manual/config', {
    method: 'POST', body: JSON.stringify({ config })
  })
}

export function startManualPipeline() {
  return aiRequest<{ status: string; batch_id?: string; message?: string }>('/pipeline/manual/start', { method: 'POST' })
}

export function getAutoPipelineConfig() {
  return aiRequest<{ config: Record<string, any> }>('/pipeline/auto/config')
}

export function saveAutoPipelineConfig(config: Record<string, any>) {
  return aiRequest<{ status: string }>('/pipeline/auto/config', {
    method: 'POST', body: JSON.stringify({ config })
  })
}

export function getSinglePipelineConfig() {
  return aiRequest<{ config: Record<string, any> }>('/pipeline/single/config')
}

export function saveSinglePipelineConfig(config: Record<string, any>) {
  return aiRequest<{ status: string }>('/pipeline/single/config', {
    method: 'POST', body: JSON.stringify({ config })
  })
}

export function getBatchCheckpointStatus(batchId: string) {
  return aiRequest<{ status: string; [key: string]: any }>('/pipeline/batch/status/' + batchId)
}

export function listBatchCheckpoints(limit: number = 20) {
  return aiRequest<{ checkpoints: any[] }>('/pipeline/batch/list?limit=' + limit)
}

export function getBatchEngineProgress(batchId: string) {
  return aiRequest<any>('/pipeline/batch/engine-progress/' + batchId)
}
 export function resetErrorJobs() {
   return aiRequest<{ count: number }>('/pipeline/jobs/reset-errors', { method: 'POST' });
 }

// Per-video results_ready (Rule ㉑: check SQLite actual data, not engine job status)
export function getResultsReady(videoId: string) {
  return aiRequest<{ video_id: string; state: string; jobs: Record<string, string>; results_ready: Record<string, boolean> }>('/results-ready/' + videoId)
}

// Per-video engine job status
export function getEngineJobStatus(videoId: string) {
  return aiRequest<{ video_id: string; jobs: Record<string, string> }>('/engine-jobs/' + videoId)
}

// Single-video pipeline
export function startSinglePipeline(videoId: string) {
  return aiRequest<{ status: string; task_id?: string; message?: string }>(
    '/pipeline/single/start',
    { method: 'POST', body: JSON.stringify({ video_id: videoId }) },
  )
}

// Single-video AI data reset
export function resetSingleAssetAI(videoId: string) {
    return aiRequest<{ status: string; deleted_engine_jobs?: number }>(
      '/pipeline/single/reset/' + videoId,
      { method: 'POST' },
    )
  }

 // ── AI Module Config (6 engine modules: scene, yolo, ocr, clip, whisper, diarization) ──

 export function getModulesConfig() {
   return aiRequest<{ config: Record<string, any> }>('/modules/config')
 }

 export function saveModulesConfig(config: Record<string, any>) {
   return aiRequest<{ status: string; config?: Record<string, any> }>('/modules/config', {
     method: 'POST', body: JSON.stringify({ config })
   })
 }

 export function getSingleModuleConfig(module: string) {
   return aiRequest<{ module: string; config: Record<string, any> }>('/modules/config/' + module)
 }

 export function saveSingleModuleConfig(module: string, config: Record<string, any>) {
   return aiRequest<{ status: string; module?: string; config?: Record<string, any> }>('/modules/config/' + module, {
     method: 'POST', body: JSON.stringify({ config })
   })
 }

// ── YOLO Tag Browse ──

export function getYoloTagBrowse(search?: string, sort?: string) {
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  if (sort) params.set('sort', sort)
  const qs = params.toString()
  return aiRequest<{ labels: Array<{ label: string; total_count: number; scene_count: number; video_count: number; avg_confidence: number }>; total: number }>('/tags/yolo/browse' + (qs ? `?${qs}` : ''))
}

export function getYoloTagVideos(label: string, page?: number) {
  const params = new URLSearchParams()
  if (page) params.set('page', String(page))
  const qs = params.toString()
  return aiRequest<{ assets: Array<{ id: string; file_name: string; duration: number; thumbnail_path: string; tag_count: number; scene_count: number }>; total: number }>('/tags/yolo/browse/' + encodeURIComponent(label) + '/videos' + (qs ? `?${qs}` : ''))
}
