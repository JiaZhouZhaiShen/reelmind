export type { ManualPipelineConfig, AutoPipelineConfig, SinglePipelineConfig } from './ai'
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
  has_audio: boolean;
  thumbnail_path?: string;
  proxy_path?: string;
  transcript_status: string;
  clip_status: string;
  scene_status: string;
  yolo_status: string;
  ocr_status: string;
  diarization_status: string;
  is_imported: boolean;
  is_archived: boolean;
  is_favorite: boolean;
  notes?: string;
  created_at: string;
  updated_at: string;
  tags: string[];
}

export interface Library {
  id: string;
  name: string;
  description?: string;
  is_external: boolean;
  import_mode: string;
  auto_scan: boolean;
  total_assets: number;
  total_size_bytes: number;
  total_duration_seconds: number;
  created_at: string;
  updated_at: string;
  paths: string[];
}

export interface SearchResult {
  id: string;
  file_name: string;
  duration?: number;
  thumbnail_path?: string;
  match_type: string;
  score: number;
  transcript_snippet?: string;
  transcript_time?: number;
}
