const BASE = '/api';

const TOKEN_KEY = 'reelmind_token';

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE}${path}`, {
    headers: { ...headers, ...((options?.headers as Record<string, string>) || {}) },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}

// ── AI Pipeline Config ──





// ── Pipeline Execution ──


    export function getPendingAssetCount(engines?: string[], max_file_size_mb?: number, max_duration_minutes?: number) {
      const params = new URLSearchParams();
      if (engines?.length) params.set("engines", engines.join(","));
      if (max_file_size_mb) params.set("max_file_size_mb", String(max_file_size_mb));
      if (max_duration_minutes) params.set("max_duration_minutes", String(max_duration_minutes));
      const qs = params.toString();
      return request<any>(`/ai/pending-count${qs ? `?${qs}` : ""}`);
    }

export function getScanStatusAI() {
  return request<{
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
  }>('/ai/scan-status');
}

export function scanLibraryAI() {
  return request<{ status: string; message: string }>('/ai/scan-library', { method: 'POST' });
}

export function scanPauseAI() {
  return request<{ status: string; message: string }>('/ai/scan-pause', { method: 'POST' });
}

export function scanResumeAI() {
  return request<{ status: string; message: string }>('/ai/scan-resume', { method: 'POST' });
}

// ── Models ──

export function getAIModelStatus() {
  return request<{ models: Record<string, boolean>; gpu: { used: number; total: number; percent: number } }>(
    '/ai/models/status',
  );
}

export function loadAIModel(modelName: string) {
  return request<{ status: string; model: string; message?: string }>(`/ai/models/load/${modelName}`, {
    method: 'POST',
  });
}

export function unloadAIModel(modelName: string) {
  return request<{ status: string; model: string }>(`/ai/models/unload/${modelName}`, { method: 'POST' });
}

export function getHFTokenStatus() {
  return request<{ set: boolean }>('/ai/models/token');
}

export function setHFToken(token: string) {
  return request<{ status: string; set: boolean }>('/ai/models/token', {
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
  return request<any>('/ai/auto-run/status');
}

// ── Cancel / Reset ──

export function cancelAIPipeline(videoId: string) {
  return request<{ status: string; task_id: string }>(`/ai/process/${videoId}/cancel`, { method: 'POST' });
}



export function resetAssetAI(id: string) {
  return request<{ status: string; video_id: string }>('/ai/reset-asset/' + id, { method: 'POST' });
}

export function batchResetAssetAI(assetIds: string[]) {
  return request<{ status: string; total: number; reset_count: number; failed_count: number; failed_ids?: string[] }>(
    '/ai/batch-reset-assets',
    { method: 'POST', body: JSON.stringify({ asset_ids: assetIds }) },
  );
}

// ── Stats ──

export function getAIStats() {
  return request<{
    videos_processed: number;
    total_scenes: number;
    total_subtitles: number;
    total_tags: number;
    total_ocr_texts: number;
    total_frames: number;
    speakers_found: number;
  }>('/ai/stats');
}

// ── AI Results (SQLite reads proxied through server) ──

export function processAI(videoId: string, videoPath: string) {
  return request('/ai/process', {
    method: 'POST',
    body: JSON.stringify({ video_id: videoId, video_path: videoPath }),
  });
}

export function getAIStatus(videoId: string) {
  return request('/ai/status/' + videoId);
}

export function getAISubtitles(videoId: string) {
  return request('/ai/subtitles/' + videoId);
}

export function getAIScenes(videoId: string) {
  return request('/ai/scenes/' + videoId);
}

export function getAIFrames(videoId: string) {
  return request('/ai/frames/' + videoId);
}

export function getAISpeakers(videoId: string) {
  return request('/ai/speakers/' + videoId);
}

export function getAITags(videoId: string) {
  return request('/ai/tags/' + videoId);
}


// ── P4: Three Independent Pipeline Configs ──

export function getManualPipelineConfig() {
  return request<{ config: Record<string, any> }>('/ai/pipeline/manual/config')
}

export function saveManualPipelineConfig(config: Record<string, any>) {
  return request<{ status: string }>('/ai/pipeline/manual/config', {
    method: 'POST', body: JSON.stringify({ config })
  })
}

export function startManualPipeline() {
  return request<{ status: string; batch_id?: string; message?: string }>('/ai/pipeline/manual/start', { method: 'POST' })
}

export function getAutoPipelineConfig() {
  return request<{ config: Record<string, any> }>('/ai/pipeline/auto/config')
}

export function saveAutoPipelineConfig(config: Record<string, any>) {
  return request<{ status: string }>('/ai/pipeline/auto/config', {
    method: 'POST', body: JSON.stringify({ config })
  })
}

export function getSinglePipelineConfig() {
  return request<{ config: Record<string, any> }>('/ai/pipeline/single/config')
}

export function saveSinglePipelineConfig(config: Record<string, any>) {
  return request<{ status: string }>('/ai/pipeline/single/config', {
    method: 'POST', body: JSON.stringify({ config })
  })
}

export function getBatchCheckpointStatus(batchId: string) {
  return request<{ status: string; [key: string]: any }>('/ai/pipeline/batch/status/' + batchId)
}

export function listBatchCheckpoints(limit: number = 20) {
  return request<{ checkpoints: any[] }>('/ai/pipeline/batch/list?limit=' + limit)
}

export function getBatchEngineProgress(batchId: string) {
  return request<any>('/ai/pipeline/batch/engine-progress/' + batchId)
}
 export function resetErrorJobs() {
   return request<{ count: number }>('/ai/pipeline/jobs/reset-errors', { method: 'POST' });
 }

// Per-video results_ready (Rule ㉑: check SQLite actual data, not engine job status)
export function getResultsReady(videoId: string) {
  return request<{ video_id: string; state: string; jobs: Record<string, string>; results_ready: Record<string, boolean> }>('/ai/results-ready/' + videoId)
}

// Per-video engine job status
export function getEngineJobStatus(videoId: string) {
  return request<{ video_id: string; jobs: Record<string, string> }>('/ai/engine-jobs/' + videoId)
}

// Single-video pipeline
export function startSinglePipeline(videoId: string) {
  return request<{ status: string; task_id?: string; message?: string }>(
    '/ai/pipeline/single/start',
    { method: 'POST', body: JSON.stringify({ video_id: videoId }) },
  )
}

// Single-video AI data reset
export function resetSingleAssetAI(videoId: string) {
    return request<{ status: string; deleted_engine_jobs?: number }>(
      '/ai/pipeline/single/reset/' + videoId,
      { method: 'POST' },
    )
  }

 // ── AI Module Config (6 engine modules: scene, yolo, ocr, clip, whisper, diarization) ──

 export function getModulesConfig() {
   return request<{ config: Record<string, any> }>('/ai/modules/config')
 }

 export function saveModulesConfig(config: Record<string, any>) {
   return request<{ status: string; config?: Record<string, any> }>('/ai/modules/config', {
     method: 'POST', body: JSON.stringify({ config })
   })
 }

 export function getSingleModuleConfig(module: string) {
   return request<{ module: string; config: Record<string, any> }>('/ai/modules/config/' + module)
 }

 export function saveSingleModuleConfig(module: string, config: Record<string, any>) {
   return request<{ status: string; module?: string; config?: Record<string, any> }>('/ai/modules/config/' + module, {
     method: 'POST', body: JSON.stringify({ config })
   })
 }
