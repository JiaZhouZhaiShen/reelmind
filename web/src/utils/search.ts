 import type { Asset, SearchResult } from "../api/client"

 export function toPseudoAsset(r: SearchResult): Asset {
   return {
     id: r.id,
     library_id: "",
     original_path: "",
     file_name: r.file_name,
     file_size: r.file_size ?? 0,
     duration: r.duration,
     thumbnail_path: r.thumbnail_path,
     is_archived: r.is_archived,
     is_favorite: r.is_favorite,
     media_date: r.media_date,
     mime_type: "video/mp4",
     has_audio: false,
     transcript_status: r.transcript_status || "",
     clip_status: "",
     scene_status: r.scene_status || "",
     yolo_status: r.has_yolo_tags ? "done" : "",
     ocr_status: r.has_ocr_text ? "done" : "",
     diarization_status: r.diarization_status || "",
     has_yolo_tags: r.has_yolo_tags,
     has_ocr_text: r.has_ocr_text,
     is_imported: true,
     codec: r.codec,
    width: r.width,
    height: r.height,
    tags: [],
    created_at: "",
    updated_at: "",
  } as unknown as Asset
}
