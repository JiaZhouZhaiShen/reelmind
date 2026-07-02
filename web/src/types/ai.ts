/** Pipeline engine state machine */
export type PipelineState = 'idle' | 'starting' | 'running' | 'paused' | 'completed' | 'error'
export type EngineStatus = 'pending' | 'running' | 'completed' | 'error'

export interface GPUInfo {
  used: number
  total: number
  percent: number
}

export interface QueueVideo {
  file_name: string
  status: string
}

export interface QueueStatus {
  status: PipelineState
  total: number
  completed: number
  failed: number
  skipped: number
  overall_progress: number
  current_video: { file_name: string } | null
  current_stage: string
  current_progress: number
  message: string
  videos: QueueVideo[]
  model_progress: Record<string, { current: number; total: number }>
}

export interface PendingCounts {
  total_assets: number
  total_pending: number
  scene_pending: number
  scene_success: number
  scene_error: number
  scene_done_count: number
  yolo_pending: number
  yolo_success: number
  yolo_error: number
  yolo_done_count: number
  ocr_pending: number
  ocr_success: number
  ocr_error: number
  ocr_done_count: number
  clip_pending: number
  clip_success: number
  clip_error: number
  clip_done_count: number
  transcript_pending: number
  transcript_success: number
  transcript_error: number
  transcript_done_count: number
  diarization_pending: number
  diarization_success: number
  diarization_error: number
  diarization_done_count: number
}

export interface PipelineProgress {
  status: string
  progress: number
  message: string
}


// ── P4: Three Independent Pipeline Configs ──

export interface ManualPipelineConfig {
  enabled: boolean
  engines: string[]
  batch_size: number
  timeout_minutes: number
  filters: {
    max_file_size_mb: number
    max_duration_minutes: number
  }
}

export interface AutoPipelineConfig {
  enabled: boolean
  engines: string[]
  batch_size: number
  time_window_start: number
  time_window_end: number
  gpu_threshold_percent: number
  check_interval_seconds: number
  filters: {
    max_file_size_mb: number
    max_duration_minutes: number
  }
}

export interface SinglePipelineConfig {
  enabled: boolean
  engines: string[]
  timeout_minutes: number
  filters: {
    max_file_size_mb: number
    max_duration_minutes: number
  }
}

export interface BatchCheckpointInfo {
  id: string
  task_label: string
  total_videos: number
  batch_size: number
  processed: number
  status: string
  created_at: string
  updated_at: string
}
