import { BASE, request, getToken, setToken, clearToken } from './base';
import * as authApi from './auth';
import * as assetsApi from './assets';
import * as systemApi from './system';
import * as tagsApi from './tags'
import * as aiApi from './ai';

export { getToken, setToken, clearToken, request };

export interface UserInfo {
  id: string;
  username: string;
  role: string;

}
export interface AuthResponse {
  token: string;
  user: UserInfo;

}
export interface Asset {
  id: string;
  library_id: string;
  original_path: string;
  file_name: string;
  file_size: number;
  file_hash?: string;
  mime_type?: string;
  width?: number;
  height?: number;
  duration?: number;
  fps?: number;
  codec?: string;
  audio_codec?: string;
  has_audio: boolean;
  thumbnail_path?: string;
  proxy_path?: string;
  transcript_status: string;
  clip_status: string;
  scene_status: string;
  yolo_status: string;
  ocr_status: string;
  has_yolo_tags?: boolean;
  has_ocr_text?: boolean;
  is_imported: boolean;
  is_archived: boolean;
  is_favorite: boolean;
  notes?: string;
  media_date?: string;
  created_at: string;
  updated_at: string;
  tags: string[];
  exif?: Record<string, unknown> | null;
  custom_metadata?: Record<string, unknown> | null;
}
export interface Library {
  id: string;
  name: string;
  description?: string;
  is_external: boolean;
  import_mode: string;
  auto_scan: boolean;
  settings?: Record<string, unknown>;
  total_assets: number;
  total_size_bytes: number;
  total_duration_seconds: number;
  created_at: string;
  updated_at: string;
  paths: string[];
  path_details?: { id: string; path: string }[];
}
export interface LibrarySettings {
  custom_video_extensions?: string[];
  excluded_extensions?: string[];
  [key: string]: unknown;
}
export interface SearchResult {
  id: string;
  file_name: string;
  duration?: number;
  thumbnail_path?: string;
  media_date?: string;
  file_size: number;
  codec?: string;
  width?: number;
  height?: number;
  is_favorite: boolean;
  is_archived: boolean;
  match_type: string;
  score: number;
  match_sources: string[];
  matches: Array<{source: string; snippet: string; time_sec: number}>;
 scene_status: string;
 transcript_status: string;
 diarization_status: string;
 has_yolo_tags: boolean;
 has_ocr_text: boolean;
}
/** Pipeline configuration — which tasks are enabled and their parameters */
export interface PipelineConfig {
  scene_threshold?: number;
  scene_enabled?: boolean;
  yolo_enabled?: boolean;
  yolo_model?: string;
  ocr_enabled?: boolean;
  clip_enabled?: boolean;
  transcript_enabled?: boolean;
  transcript_model?: string;
  diarization_enabled?: boolean;
  [key: string]: unknown;
}

export interface SystemStats {
  total_assets: number;
  total_libraries: number;
  total_size_bytes: number;
  total_duration_seconds: number;
  pending_jobs: number;
  libraries: Library[];
}
export interface MetadataFieldDef {
  key: string;
  label: string;
  description: string;
  category: string;
  group: string;
}
export interface MetadataFieldListResponse {
  fields: MetadataFieldDef[];
  groups: string[];
}
export interface ScanStatus {
  status: string;
  total: number;
  completed: number;
  failed: number;
  paused: boolean;
  current_video: { video_id: string; file_name: string } | null;
  current_stage: string;
  current_progress: number;
  overall_progress: number;
  message: string;
  skipped: number;
  current_index: number;
  model_progress: Record<string, { current: number; total: number }>;
  videos: any[];
}
export interface TagInfo {
  id: string;
  name: string;
  category: string;
  color?: string;
  usage_count: number;
  created_at: string;
}
export interface AssetTagInfo {
  id: string;
  tag_id: string;
  tag_name: string;
  category: string;
  color?: string;
  confidence?: number;
  source: string;
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
  containers: Record<string, {
    status: string
    cpu_percent: number
    memory_mb: number
    memory_limit_mb: number
    memory_percent: number
    error?: string
  }>
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

export const api = {
  ...authApi,
  ...assetsApi,
  ...systemApi,
  ...tagsApi,
  ...aiApi,
};
