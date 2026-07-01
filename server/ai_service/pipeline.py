"""AI Processing Pipeline -- sequenced task orchestration.

Pipeline order:
  1. TransNetV2 -> scene cuts
  2. For each scene: YOLO + OCR + CLIP (parallel per scene, CUDA serial)
  3. Audio chain: Whisper -> diarization (merge speakers)

Config sourced from configs/ — each module + pipeline runner has its own file.
"""

from __future__ import annotations
import json
import threading
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
import ssl as _ssl
import subprocess
import sys
import urllib.request as _ur
_original_urlopen = _ur.urlopen
def _patched_urlopen(url, *args, **kwargs):
    if 'hf-mirror.com' in str(url) or 'hf-mirror' in str(url):
        kwargs['context'] = _ssl._create_unverified_context()
    return _original_urlopen(url, *args, **kwargs)
_ur.urlopen = _patched_urlopen

from configs import scene as scene_cfg, yolo as yolo_cfg, ocr as ocr_cfg, clip as clip_cfg, whisper as whisper_cfg, diarization as diarization_cfg, pipeline as pipeline_cfg

logger = logging.getLogger(__name__)

_pre_loaded_models: set = set()

def _update_model_state(model_name: str, loaded: bool):
    """Update the shared model state dict tracked by main.py."""
    from main import _model_states, _model_lock
    with _model_lock:
        _model_states[model_name] = loaded

_JOB_DEPS = {"clip": ["scene"], "diarization": ["transcript"], "yolo": ["scene"], "ocr": ["scene"]}

def _upsert_job(md, media_id_str: str, engine: str, status: str):
    """Dual-write: upsert ai_engine_jobs alongside old Asset fields."""
    from sqlalchemy import text
    try:
        deps = _JOB_DEPS.get(engine, [])
        md.execute(
            text("""INSERT INTO ai_engine_jobs (media_id, engine_name, status, depends_on, completed_at)
                     VALUES (:mid, :eng, :st, :deps, NOW())
                     ON CONFLICT (media_id, engine_name)
                     DO UPDATE SET status = :st2, completed_at = NOW(), error_message = NULL"""),
            {"mid": media_id_str, "eng": engine, "st": status, "deps": deps, "st2": status},
        )
        md.commit()
    except Exception:
        logger.warning("ai_engine_jobs upsert failed for %s/%s", media_id_str, engine)


def _set_job_status(media_id, engine, status):
    """Self-contained upsert of ai_engine_jobs (opens/closes its own PG session).

    Follows Rule 1 and Rule 6: AI Worker only writes PG via ai_engine_jobs,
    and ai_engine_jobs is the single write entry point for pipeline status.
    """
    try:
        from models.db import get_pg_session
        s = get_pg_session()
        try:
            _upsert_job(s, media_id, engine, status)
        finally:
            s.close()
    except Exception as e:
        logger.warning("Failed to set %s job status for %s: %s", engine, media_id, e)

def get_pipeline_steps() -> dict:
    """Return full config as dict (backward-compatible with /config API)."""
    from configs import to_dict_all
    return to_dict_all()

def set_pipeline_steps(config: dict):
    """Update config from dict (backward-compatible with POST /config)."""
    from configs import update_from_dict
    update_from_dict(config)

class AIPipeline:
    """Manages the end-to-end AI processing sequence for a video."""

    def __init__(self, video_id: str, video_path: str, progress_callback: Callable | None = None):
        self.video_id = video_id
        self.video_path = video_path
        self.progress_callback = progress_callback or (lambda msg, pct: None)
        self._session = None

    def _get_session(self):
        if self._session is None:
            from models.ai_models import get_ai_session
            self._session = get_ai_session()
        return self._session

    def _close_session(self):
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    def _progress(self, message: str, pct: float):
        logger.info("[%s] %.0f%% %s", self.video_id, pct, message)
        self.progress_callback(message, pct)

    def run(self):
        """Execute the full pipeline."""
        from models.ai_models import Video, Scene, Frame, Subtitle, SceneTag, SceneOCR, get_ai_session
        from main import _model_states as _ms_run, _model_lock as _ml_run
        global _pre_loaded_models; _pre_loaded_models = set()
        with _ml_run:
            for _k, _v in _ms_run.items():
                if _v: _pre_loaded_models.add(_k)

        video_path = Path(self.video_path)
        if not video_path.exists():
            self._progress(f"Video not found: {video_path}", 0)
            return {"status": "error", "message": "Video not found"}

        try:
            # ── Step 0: Ensure video record exists ──
            session = self._get_session()
            video = session.query(Video).filter(Video.id == self.video_id).first()
            if not video:
                import cv2
                cap = cv2.VideoCapture(str(video_path))
                duration = cap.get(cv2.CAP_PROP_FPS) and cap.get(cv2.CAP_PROP_FRAME_COUNT)
                fps = cap.get(cv2.CAP_PROP_FPS)
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                if fps > 0:
                    duration = duration / fps
                video = Video(
                    id=self.video_id,
                    file_path=str(video_path),
                    file_name=video_path.name,
                    duration=float(duration or 0),
                    width=width, height=height,
                    fps=float(fps or 0),
                )
                session.add(video)
                session.commit()

            # ── Step 1: Scene cut (TransNetV2) ──
            if (engines is None or "scene" in engines) and scene_cfg.enabled:
                self._progress("Scene detection (TransNetV2)...", 5)
                _update_model_state("transnet", True)
                from services.scene_service import detect_scenes, extract_thumbnail
                scenes_data = detect_scenes(str(video_path))
                self._progress(f"Found {len(scenes_data)} scenes", 15)
            else:
                self._progress("Scene detection skipped", 15)
                scenes_data = []

            thumb_dir = Path(os.environ.get("CACHE_ROOT", "cache")) / "scene-thumbnails" / self.video_id
            thumb_dir.mkdir(parents=True, exist_ok=True)

            scene_records = []
            if not scenes_data:
                import cv2 as _cv2
                _cap = _cv2.VideoCapture(str(video_path))
                _duration = 0
                _fps = _cap.get(_cv2.CAP_PROP_FPS)
                _total_frames = int(_cap.get(_cv2.CAP_PROP_FRAME_COUNT))
                if _fps > 0:
                    _duration = _total_frames / _fps
                _cap.release()
                scene = Scene(
                    video_id=self.video_id, scene_index=0,
                    start_time=0, end_time=_duration,
                )
                session.add(scene)
                session.flush()
                scene_records = [scene]
                self._progress("Using single full-video scene", 20)
            else:
                for sc_idx, sc in enumerate(scenes_data):
                    scene = Scene(
                        video_id=self.video_id, scene_index=sc["index"],
                        start_time=sc["start_time"], end_time=sc["end_time"],
                    )
                    thumb_path = thumb_dir / f"scene_{sc['index']:04d}.jpg"
                    if not thumb_path.exists():
                        extract_thumbnail(str(video_path), sc["thumbnail_time"], str(thumb_path))
                    scene.thumbnail_path = str(thumb_path.resolve())
                    session.add(scene)
                    session.flush()
                    scene_records.append(scene)

            session.commit()
            self._progress(f"Saved {len(scene_records)} scenes", 20)
            total_scenes = len(scene_records)
            enabled_steps = []
            if (engines is None or "yolo" in engines) and yolo_cfg.enabled: enabled_steps.append("yolo")
            if (engines is None or "ocr" in engines) and ocr_cfg.enabled: enabled_steps.append("ocr")
            if (engines is None or "clip" in engines) and clip_cfg.enabled: enabled_steps.append("clip")
            step_count = len(enabled_steps) or 1

            # ── Step 2: YOLO batch ──
            if (engines is None or "yolo" in engines) and yolo_cfg.enabled:
                self._progress(f"YOLO object detection ({total_scenes} scenes)...", 20)
                _update_model_state("yolo", True)
                from services.yolo_service import detect_scene_objects, _unload_yolo
                for sc_idx, scene in enumerate(scene_records):
                    try:
                        objects = detect_scene_objects(
                            str(video_path), scene.start_time, scene.end_time
                        )
                        for obj in objects:
                            tag = SceneTag(
                                scene_id=scene.id, label=obj["label"],
                                confidence=obj["confidence"], count=obj["count"],
                            )
                            session.add(tag)
                        session.commit()
                    except Exception as e:
                        logger.error("YOLO failed for scene %s: %s", scene.id, e)
                    self._progress(f"YOLO [{sc_idx+1}/{total_scenes}]",
                        20 + (sc_idx + 1) / total_scenes * (20 / step_count))
                if "yolo" not in _pre_loaded_models:
                    _unload_yolo()
                if "yolo" not in _pre_loaded_models: _update_model_state("yolo", False)
                _set_job_status(self.video_id, "yolo", "completed")

            # ── Step 3: OCR batch ──
            if (engines is None or "ocr" in engines) and ocr_cfg.enabled:
                ocr_start = 20 + (20 / step_count) * enabled_steps.index("ocr")
                self._progress(f"OCR text recognition ({total_scenes} scenes)...", ocr_start)
                _update_model_state("ocr", True)
                from services.ocr_service import ocr_scene_middle, _unload_ocr
                for sc_idx, scene in enumerate(scene_records):
                    try:
                        mid_time = (scene.start_time + scene.end_time) / 2
                        ocr_results = ocr_scene_middle(str(video_path), mid_time)
                        for ocr_item in ocr_results:
                            ocr_rec = SceneOCR(
                                scene_id=scene.id, text=ocr_item["text"],
                                confidence=ocr_item["confidence"],
                                bbox_x=ocr_item["bbox"]["x"], bbox_y=ocr_item["bbox"]["y"],
                                bbox_w=ocr_item["bbox"]["w"], bbox_h=ocr_item["bbox"]["h"],
                            )
                            session.add(ocr_rec)
                        session.commit()
                    except Exception as e:
                        logger.error("OCR failed for scene %s: %s", scene.id, e)
                    self._progress(f"OCR [{sc_idx+1}/{total_scenes}]",
                        ocr_start + (sc_idx + 1) / total_scenes * (20 / step_count))
                if "ocr" not in _pre_loaded_models:
                    _unload_ocr()
                if "ocr" not in _pre_loaded_models: _update_model_state("ocr", False)
                _set_job_status(self.video_id, "ocr", "completed")

            # ── Step 4: CLIP batch ──
            _clip_ok = False
            if (engines is None or "clip" in engines) and clip_cfg.enabled:
                if not os.environ.get('ENABLE_CLIP', 'false') == 'true':
                    self._progress("CLIP disabled by config (ENABLE_CLIP=false)", 40)
                else:
                    clip_start = 20 + (20 / step_count) * enabled_steps.index("clip")
                    self._progress(f"CLIP encoding ({total_scenes} scenes)...", clip_start)
                    clip_mid_times = [(sc.start_time + sc.end_time) / 2 for sc in scene_records]
                    from services.clip_service import encode_frames, _unload_clip
                    _update_model_state("clip", True)
                    try:
                        frame_embeddings = encode_frames(str(video_path), clip_mid_times)
                        _clip_ok = bool(frame_embeddings)
                    except Exception as e:
                        logger.error("CLIP batch encode failed: %s", e)
                        frame_embeddings = []
                    for sc_idx, scene in enumerate(scene_records):
                        try:
                            mid_time = (scene.start_time + scene.end_time) / 2
                            fe = None
                            for emb in frame_embeddings:
                                if emb["time_sec"] == mid_time:
                                    fe = emb
                                    break
                            if fe:
                                frame_rec = Frame(
                                    video_id=self.video_id, scene_id=scene.id,
                                    time_sec=fe["time_sec"], embedding=fe["embedding"],
                                )
                                session.add(frame_rec)
                            session.commit()
                        except Exception as e:
                            logger.error("CLIP encoding failed for scene %s: %s", scene.id, e)
                        self._progress(f"CLIP [{sc_idx+1}/{total_scenes}]",
                            clip_start + (sc_idx + 1) / total_scenes * (20 / step_count))
                    if "clip" not in _pre_loaded_models:
                        _unload_clip()
                    if "clip" not in _pre_loaded_models: _update_model_state("clip", False)
            else:
                self._progress("CLIP step skipped by config", 40)

            self._progress("Scene processing complete", 40)

            # ── Step 5: Audio chain (Whisper -> Diarization) ──
            subtitles_data = []
            if (engines is None or "transcript" in engines) and whisper_cfg.enabled:
                if not os.environ.get('ENABLE_WHISPER', 'false') == 'true':
                    self._progress("Whisper disabled by config (ENABLE_WHISPER=false)", 80)
                else:
                    self._progress("Transcribing audio (Whisper)...", 80)
                    _update_model_state("whisper", True)
                    from services.whisper_service import transcribe
                    try:
                        subtitles_data = transcribe(str(video_path))
                    except Exception as e:
                        logger.error("Whisper transcribe failed: %s", e)
                        subtitles_data = []

                    if subtitles_data:
                        for sub in subtitles_data:
                            sub_rec = Subtitle(
                                video_id=self.video_id, start=sub["start"], end=sub["end"],
                                text=sub["text"], language=sub.get("language", "zh"),
                            )
                            session.add(sub_rec)
                        session.commit()
                        self._progress(f"Transcribed {len(subtitles_data)} segments", 87)

                        if (engines is None or "diarization" in engines) and diarization_cfg.enabled:
                            self._progress("Speaker diarization (pyannote)...", 87)
                            from services.diarization_service import process as diarize
                            merged_subs = diarize(str(video_path), subtitles_data)
                            for sub_data in merged_subs:
                                if sub_data.get("speaker"):
                                    existing = session.query(Subtitle).filter(
                                        Subtitle.video_id == self.video_id,
                                        Subtitle.start == sub_data["start"],
                                        Subtitle.end == sub_data["end"],
                                    ).first()
                                    if existing:
                                        existing.speaker = sub_data["speaker"]
                            session.commit()
                            speakers = set(s.get("speaker") for s in merged_subs if s.get("speaker"))
                            self._progress(f"Diarization done: {len(speakers)} speakers found", 95)
                        else:
                            self._progress("Speaker diarization skipped", 93)
                    else:
                        self._progress("No speech detected", 87)
            else:
                self._progress("Transcription skipped", 80)

            # ── Update ai_engine_jobs status ──
            if (engines is None or "scene" in engines) and scene_cfg.enabled:
                _set_job_status(self.video_id, "scene", "completed")
            if whisper_cfg.enabled and os.environ.get('ENABLE_WHISPER', 'false') == 'true':
                _set_job_status(self.video_id, "transcript", "completed")
            if clip_cfg.enabled and os.environ.get('ENABLE_CLIP', 'false') == 'true' and _clip_ok:
                _set_job_status(self.video_id, "clip", "completed")
            if diarization_cfg.enabled and subtitles_data:
                _set_job_status(self.video_id, "diarization", "completed")

            # ── Generate WebVTT if subtitles were produced ──
            if subtitles_data:
                try:
                    cache_root = Path(os.environ.get("CACHE_ROOT", "cache"))
                    vtt_dir = cache_root / "webvtt"
                    vtt_dir.mkdir(parents=True, exist_ok=True)
                    vtt_path = vtt_dir / f"{self.video_id}.vtt"
                    with open(vtt_path, "w", encoding="utf-8") as fh:
                        fh.write("WEBVTT\n\n")
                        for sub in subtitles_data:
                            start_h = int(sub["start"] // 3600)
                            start_m = int((sub["start"] % 3600) // 60)
                            start_s = sub["start"] % 60
                            end_h = int(sub["end"] // 3600)
                            end_m = int((sub["end"] % 3600) // 60)
                            end_s = sub["end"] % 60
                            fh.write(f"{start_h:02d}:{start_m:02d}:{start_s:06.3f} --> {end_h:02d}:{end_m:02d}:{end_s:06.3f}\n")
                            fh.write(f"{sub['text']}\n\n")
                    logger.info("WebVTT generated: %s (%d segments)", vtt_path, len(subtitles_data))
                    try:
                        from models.db import get_pg_session as _ssf
                        import uuid
                        _db2 = _ssf()
                        _a2 = _db2.query(_Asset).filter(_Asset.id == uuid.UUID(self.video_id)).first()
                        if _a2:
                            _a2.webvtt_path = str(vtt_path.resolve())
                            _db2.commit()
                        _db2.close()
                    except Exception as _e2:
                        logger.warning("Failed to update webvtt_path: %s", _e2)
                except Exception as _e:
                    logger.warning("Failed to generate WebVTT: %s", _e)

            self._progress("AI pipeline complete!", 100)
            return {"status": "done"}

        except Exception as e:
            self._progress(f"Pipeline failed: {e}", 0)
            logger.exception("Pipeline failed for video %s", self.video_id)
            return {"status": "error", "message": str(e)}
        finally:
            self._close_session()

def process_batch(
    pending_assets: list,
    engines: list[str] | None = None,
    filters: dict | None = None,
    progress_callback: Callable | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Batch pipeline: each model processes ALL pending items before next model loads."""
    import uuid as _uuid
    import cv2 as _cv2
    from pathlib import Path as _Path
    from models.ai_models import Video as _AIVideo, Scene as _Scene, SceneTag as _SceneTag, SceneOCR as _SceneOCR, Frame as _Frame, Subtitle as _Subtitle, get_ai_session

    # Record which models were already loaded (manually) before this batch
    from main import _model_states as _ms3, _model_lock as _ml3
    global _pre_loaded_models; _pre_loaded_models = set()
    with _ml3:
        for _k, _v in _ms3.items():
            if _v: _pre_loaded_models.add(_k)

    total = len(pending_assets)
    step_results = {"completed": 0, "failed": 0, "skipped": 0}

    # Filter out assets whose video files no longer exist on disk
    existing_assets = []
    missing_assets = []
    for _asset in pending_assets:
        if _asset.original_path and os.path.isfile(str(_asset.original_path)):
            existing_assets.append(_asset)
        else:
            missing_assets.append(_asset)
            step_results["skipped"] += 1
            step_results["failed"] += 1  # count as "failed" so completed calc is honest
            for _eng in ("scene", "yolo", "ocr", "clip", "transcript", "diarization"):
                _set_job_status(str(_asset.id), _eng, "error")
    if missing_assets:
        logger.warning("Batch skipped %d assets with missing files: %s",
            len(missing_assets), [a.file_name for a in missing_assets])
    pending_assets = existing_assets
    total = len(pending_assets)

    # Apply file filtering rules (Rule 15: filtering on AI side)
    _filters = filters or {}
    _max_size = _filters.get("max_file_size_mb", 0)
    _max_duration = _filters.get("max_duration_minutes", 0)
    _skip_rendered = _filters.get("skip_rendered_files", False)
    _ALL_ENGINES = ("scene", "yolo", "ocr", "clip", "transcript", "diarization")

    if _max_size > 0 or _skip_rendered or _max_duration > 0:
        _filtered = []
        for _asset in pending_assets:
            _skip = False
            _fname = _Path(_asset.original_path).name

            # File size check
            if _max_size > 0:
                _size_mb = os.path.getsize(str(_asset.original_path)) / (1024 * 1024)
                if _size_mb > _max_size:
                    logger.info("Filtered %s: size %.0fMB > %dMB limit", _fname, _size_mb, _max_size)
                    _skip = True

            # Skip Premiere Pro rendered files
            if not _skip and _skip_rendered and _fname.startswith("Rendered - ") and _fname.lower().endswith(".mov"):
                logger.info("Filtered %s: Premiere Pro rendered file", _fname)
                _skip = True

            # Duration check
            if not _skip and _max_duration > 0:
                try:
                    import subprocess
                    _result = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", str(_asset.original_path)],
                        capture_output=True, text=True, timeout=30)
                    if _result.returncode == 0 and _result.stdout.strip():
                        _dur = float(_result.stdout.strip())
                        if _dur > _max_duration * 60:
                            logger.info("Filtered %s: duration %.0fs > %dmin limit", _fname, _dur, _max_duration)
                            _skip = True
                except Exception:
                    pass

            if _skip:
                for _eng in _ALL_ENGINES:
                    _set_job_status(str(_asset.id), _eng, "error")
                step_results["skipped"] += 1
                step_results["failed"] += 1
            else:
                _filtered.append(_asset)

        _skipped_count = len(pending_assets) - len(_filtered)
        if _skipped_count:
            logger.warning("Batch filtered %d assets by config rules", _skipped_count)
        pending_assets = _filtered

    total = len(pending_assets)

    def _cb(msg: str, pct: float):
        logger.info("[batch] %.0f%% %s", pct, msg)
        if progress_callback:
            progress_callback(msg, pct)

    if total == 0:
        _cb("All assets skipped — files not found or filtered", 0)
        return step_results

    # ══════════════════════════════════════════
    # STEP 1: TransNetV2 — scene detection
    # ══════════════════════════════════════════
    if (engines is None or "scene" in engines) and scene_cfg.enabled:
        from services.scene_service import _load_transnet, _unload_transnet, detect_scenes, extract_thumbnail as _extract_thumb
        if cancel_event and cancel_event.is_set():
            _cb("Cancelled before TransNetV2 step", 0)
            step_results["skipped"] = len(pending_assets)
            return step_results
        _load_transnet()
        _update_model_state("transnet", True)
        try:
            ai_s = get_ai_session()
            # Re-run mode: delete existing SQLite records so all videos get fresh processing
            _rerun_count = 0
            for _asset in pending_assets:
                _existing = ai_s.query(_AIVideo).filter(_AIVideo.id == str(_asset.id)).first()
                if _existing:
                    # Delete scene thumbnail files from disk
                    for _scene in _existing.scenes:
                        if _scene.thumbnail_path:
                            try:
                                _Path(_scene.thumbnail_path).unlink(missing_ok=True)
                            except Exception:
                                pass
                    # Delete frame image files from disk
                    for _frame in _existing.frames:
                        if _frame.frame_path:
                            try:
                                _Path(_frame.frame_path).unlink(missing_ok=True)
                            except Exception:
                                pass
                    ai_s.delete(_existing)
                    _rerun_count += 1
            if _rerun_count > 0:
                ai_s.commit()
                logger.warning("Re-run mode: deleted %d existing video records, will re-process", _rerun_count)
            need = list(pending_assets)
            _cb(f"Step 1/5: TransNetV2 — {len(need)} videos to process, {total - len(need)} already done", 0)
            thumb_base = _Path(os.environ.get("CACHE_ROOT", "cache")) / "scene-thumbnails"
            for idx, asset in enumerate(need):
                if cancel_event and cancel_event.is_set():
                    _cb('Cancelled during TransNetV2 step', 0)
                    break
                try:
                    vp = str(asset.original_path)
                    cap = _cv2.VideoCapture(vp)
                    dur, fps = 0, cap.get(_cv2.CAP_PROP_FPS)
                    tf = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
                    if fps > 0: dur = tf / fps
                    w, h = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
                    cap.release()
                    video = _AIVideo(id=str(asset.id), file_path=vp, file_name=asset.file_name or _Path(vp).name,
                        duration=float(dur or 0), width=w, height=h, fps=float(fps or 0))
                    ai_s.add(video)
                    ai_s.flush()
                    scenes_data = json.loads(subprocess.run([sys.executable, '/app/services/scene_worker.py', vp], capture_output=True, text=True, timeout=300, cwd='/app').stdout)
                    thumb_dir = thumb_base / str(asset.id)
                    thumb_dir.mkdir(parents=True, exist_ok=True)
                    for sc in scenes_data:
                        scene = _Scene(video_id=str(asset.id), scene_index=sc["index"],
                            start_time=sc["start_time"], end_time=sc["end_time"])
                        tp = thumb_dir / f"scene_{sc['index']:04d}.jpg"
                        _extract_thumb(vp, sc["thumbnail_time"], str(tp))
                        scene.thumbnail_path = str(tp.resolve())
                        ai_s.add(scene)
                    ai_s.commit()
                    _set_job_status(str(asset.id), "scene", "completed")
                    step_results["completed"] += 1
                    _cb(f"[{asset.file_name}] TransNetV2 [{idx+1}/{len(need)}]", (idx + 1) / len(need) * 100)
                except Exception as e:
                    step_results["failed"] += 1
                    logger.exception("TransNetV2 failed for %s", asset.file_name)
                    try:
                        ai_s.rollback()
                    except Exception:
                        pass
            ai_s.close()
        finally:
            if "transnet" not in _pre_loaded_models:
                _unload_transnet()
            if "transnet" not in _pre_loaded_models: _update_model_state("transnet", False)
        _cb("Step 1/5: TransNetV2 done", 20)
        for _a_sc in pending_assets:
            _set_job_status(str(_a_sc.id), "scene", "completed")
    else:
        _cb("Step 1/5: TransNetV2 skipped", 20)

    # Build set of batch video IDs to scope YOLO/OCR/CLIP queries
    _batch_video_ids = set(str(a.id) for a in pending_assets)

    # ══════════════════════════════════════════
    # STEP 2: YOLO
    # ══════════════════════════════════════════
    if (engines is None or "yolo" in engines) and yolo_cfg.enabled:
        from services.yolo_service import detect_scene_objects as _detect_objects
        if cancel_event and cancel_event.is_set():
            _cb("Cancelled before YOLO step", 20)
            step_results["skipped"] = len(pending_assets)
            return step_results
        ai_s = get_ai_session()
        scenes_no_tag = ai_s.query(_Scene).outerjoin(_SceneTag, _Scene.id == _SceneTag.scene_id).filter(_SceneTag.id.is_(None), _Scene.video_id.in_(_batch_video_ids)).all()
        ai_s.close()
        _cb(f"Step 2/5: YOLO — {len(scenes_no_tag)} scenes to process", 20)
        if scenes_no_tag:
            from services.yolo_service import _load_yolo, _unload_yolo
            _load_yolo()
            _update_model_state("yolo", True)
            try:
                ai_s = get_ai_session()
                for idx, scene in enumerate(scenes_no_tag):
                    if cancel_event and cancel_event.is_set():
                        _cb('Cancelled during YOLO step', 20)
                        break
                    try:
                        video = ai_s.query(_AIVideo).filter(_AIVideo.id == scene.video_id).first()
                        if not video: continue
                        objects = _detect_objects(video.file_path, scene.start_time, scene.end_time)
                        for obj in objects:
                            ai_s.add(_SceneTag(scene_id=scene.id, label=obj["label"],
                                confidence=obj["confidence"], count=obj["count"]))
                        ai_s.commit()
                        _cb(f"YOLO [{idx+1}/{len(scenes_no_tag)}] scene {scene.scene_index}",
                            20 + (idx + 1) / len(scenes_no_tag) * 20)
                    except Exception as e:
                        try:
                            ai_s.rollback()
                        except Exception:
                            pass
                        logger.error("YOLO failed for scene %s: %s", scene.id, e)
                ai_s.close()
            finally:
                if "yolo" not in _pre_loaded_models:
                    _unload_yolo()
                if "yolo" not in _pre_loaded_models: _update_model_state("yolo", False)
        _cb("Step 2/5: YOLO done", 40)
        for _a in pending_assets:
            _set_job_status(str(_a.id), "yolo", "completed")

    else:
        _cb("Step 2/5: YOLO skipped", 40)

    # ══════════════════════════════════════════
    # STEP 3: OCR
    # ══════════════════════════════════════════
    if (engines is None or "ocr" in engines) and ocr_cfg.enabled:
        from services.ocr_service import ocr_scene_middle as _ocr_scene
        if cancel_event and cancel_event.is_set():
            _cb("Cancelled before OCR step", 40)
            step_results["skipped"] = len(pending_assets)
            return step_results
        ai_s = get_ai_session()
        scenes_no_ocr = ai_s.query(_Scene).outerjoin(_SceneOCR, _Scene.id == _SceneOCR.scene_id).filter(_SceneOCR.id.is_(None), _Scene.video_id.in_(_batch_video_ids)).all()
        ai_s.close()
        _cb(f"Step 3/5: OCR — {len(scenes_no_ocr)} scenes to process", 40)
        if scenes_no_ocr:
            from services.ocr_service import _load_ocr, _unload_ocr
            _load_ocr()
            _update_model_state("ocr", True)
            try:
                ai_s = get_ai_session()
                for idx, scene in enumerate(scenes_no_ocr):
                    if cancel_event and cancel_event.is_set():
                        _cb('Cancelled during OCR step', 40)
                        break
                    try:
                        video = ai_s.query(_AIVideo).filter(_AIVideo.id == scene.video_id).first()
                        if not video: continue
                        mid_time = (scene.start_time + scene.end_time) / 2
                        ocr_results = _ocr_scene(video.file_path, mid_time)
                        for oi in ocr_results:
                            ai_s.add(_SceneOCR(scene_id=scene.id, text=oi["text"], confidence=oi["confidence"],
                                bbox_x=oi["bbox"]["x"], bbox_y=oi["bbox"]["y"],
                                bbox_w=oi["bbox"]["w"], bbox_h=oi["bbox"]["h"]))
                        ai_s.commit()
                        _cb(f"OCR [{idx+1}/{len(scenes_no_ocr)}] scene {scene.scene_index}",
                            40 + (idx + 1) / len(scenes_no_ocr) * 20)
                    except Exception as e:
                        try:
                            ai_s.rollback()
                        except Exception:
                            pass
                        logger.error("OCR failed for scene %s: %s", scene.id, e)
                ai_s.close()
            finally:
                if "ocr" not in _pre_loaded_models:
                    _unload_ocr()
                if "ocr" not in _pre_loaded_models: _update_model_state("ocr", False)
        _cb("Step 3/5: OCR done", 60)
        for _a in pending_assets:
            _set_job_status(str(_a.id), "ocr", "completed")

    else:
        _cb("Step 3/5: OCR skipped", 60)

    # ══════════════════════════════════════════
    # STEP 4: CLIP
    # ══════════════════════════════════════════
    if (engines is None or "clip" in engines) and clip_cfg.enabled:
        from services.clip_service import encode_frames as _encode_frames
        if cancel_event and cancel_event.is_set():
            _cb("Cancelled before CLIP step", 60)
            step_results["skipped"] = len(pending_assets)
            return step_results
        ai_s = get_ai_session()
        scenes_no_frame = ai_s.query(_Scene).outerjoin(_Frame, _Scene.id == _Frame.scene_id).filter(_Frame.id.is_(None), _Scene.video_id.in_(_batch_video_ids)).all()
        ai_s.close()
        _cb(f"Step 4/5: CLIP — {len(scenes_no_frame)} scenes to process", 60)
        if scenes_no_frame:
            from services.clip_service import _load_clip, _unload_clip
            _load_clip()
            _update_model_state("clip", True)
            try:
                vid_scenes: dict = {}
                for sc in scenes_no_frame: vid_scenes.setdefault(sc.video_id, []).append(sc)
                for vdx, (vid, sc_list) in enumerate(vid_scenes.items()):
                    if cancel_event and cancel_event.is_set():
                        _cb('Cancelled during CLIP step', 60)
                        break
                    try:
                        ai_s = get_ai_session()
                        video = ai_s.query(_AIVideo).filter(_AIVideo.id == vid).first()
                        if not video: ai_s.close(); continue
                        ai_s.close()
                        mid_times = [(sc.start_time + sc.end_time) / 2 for sc in sc_list]
                        embs = _encode_frames(video.file_path, mid_times)
                        ai_s = get_ai_session()
                        for scene, emb in zip(sc_list, embs):
                            ai_s.add(_Frame(video_id=vid, scene_id=scene.id,
                                time_sec=emb["time_sec"], embedding=emb["embedding"]))
                        ai_s.commit(); ai_s.close()
                        _cb(f"CLIP [{vdx+1}/{len(vid_scenes)}] {len(sc_list)} scenes",
                            60 + (vdx + 1) / len(vid_scenes) * 20)
                    except Exception as e:
                        try:
                            ai_s.rollback()
                            ai_s.close()
                        except Exception:
                            pass
                        logger.error("CLIP failed for video %s: %s", vid, e)
                _cb("Step 4/5: CLIP done", 80)
                for _a in pending_assets:
                    _set_job_status(str(_a.id), "clip", "completed")

            finally:
                if "clip" not in _pre_loaded_models:
                    _unload_clip()
                if "clip" not in _pre_loaded_models: _update_model_state("clip", False)
    else:
        _cb("Step 4/5: CLIP skipped", 80)

    # ══════════════════════════════════════════
    # STEP 5: Whisper
    # ══════════════════════════════════════════
    if (engines is None or "transcript" in engines) and whisper_cfg.enabled:
        from services.whisper_service import transcribe as _transcribe, _unload_whisper
        if cancel_event and cancel_event.is_set():
            _cb("Cancelled before Whisper step", 80)
            step_results["skipped"] = len(pending_assets)
            return step_results
        need_whisper = list(pending_assets)
        _cb(f"Step 5/5: Whisper — {len(need_whisper)} videos to transcribe", 80)
        if need_whisper:
            try:
                for idx, asset in enumerate(need_whisper):
                    if cancel_event and cancel_event.is_set():
                        _cb('Cancelled during Whisper step', 80)
                        break
                    try:
                        vp = str(asset.original_path)
                        if not os.path.isfile(vp):
                            _set_job_status(str(asset.id), "transcript", "error")
                            if (engines is None or "diarization" in engines) and diarization_cfg.enabled:
                                _set_job_status(str(asset.id), "diarization", "error")
                            step_results["skipped"] += 1
                            continue
                        _update_model_state("whisper", True)
                        subs = _transcribe(vp)
                        ai_s = get_ai_session()
                        if subs:
                            for sub in subs:
                                ai_s.add(_Subtitle(video_id=str(asset.id), start=sub["start"],
                                    end=sub["end"], text=sub["text"], language=sub.get("language", "zh")))
                            ai_s.commit()
                        _set_job_status(str(asset.id), "transcript", "completed")
                        if (engines is None or "diarization" in engines) and diarization_cfg.enabled:
                            _set_job_status(str(asset.id), "diarization", "completed")
                        ai_s.close()
                        _cb(f"[{asset.file_name}] Whisper [{idx+1}/{len(need_whisper)}]",
                            80 + (idx + 1) / len(need_whisper) * 20)
                    except Exception as e:
                        step_results["failed"] += 1
                        logger.exception("Whisper failed for %s", asset.file_name)
            finally:
                if "whisper" not in _pre_loaded_models:
                    _unload_whisper()
                if "whisper" not in _pre_loaded_models: _update_model_state("whisper", False)
        _cb("Step 5/5: Whisper done", 100)
    else:
        _cb("Step 5/5: Whisper skipped", 100)

    # Final: unload only non-pre-loaded models
    from services.yolo_service import _unload_yolo as _uy
    if "yolo" not in _pre_loaded_models:
        _uy()
    if "yolo" not in _pre_loaded_models: _update_model_state("yolo", False)
    from services.ocr_service import _unload_ocr as _uo
    if "ocr" not in _pre_loaded_models:
        _uo()
    if "ocr" not in _pre_loaded_models: _update_model_state("ocr", False)
    from services.clip_service import _unload_clip as _uc
    if "clip" not in _pre_loaded_models:
        _uc()
    if "clip" not in _pre_loaded_models: _update_model_state("clip", False)
    from services.whisper_service import _unload_whisper as _uw
    if "whisper" not in _pre_loaded_models:
        _uw()
    if "whisper" not in _pre_loaded_models: _update_model_state("whisper", False)
    from services.scene_service import _unload_transnet as _ut
    if "transnet" not in _pre_loaded_models:
        _ut()
    if "transnet" not in _pre_loaded_models: _update_model_state("transnet", False)
    from services.diarization_service import _unload_diarization as _ud
    if "diarization" not in _pre_loaded_models:
        _ud()
    if "diarization" not in _pre_loaded_models: _update_model_state("diarization", False)

    # Final: compute actual completed count (total minus confirmed failures minus skipped)
    step_results["completed"] = len(pending_assets) - step_results["failed"] - step_results["skipped"]
    if step_results["completed"] < 0:
        step_results["completed"] = 0
    _cb("Batch pipeline complete!", 100)
    logger.info("Batch pipeline done: %d completed, %d failed, %d skipped",
        step_results["completed"], step_results["failed"], step_results["skipped"])
    return step_results
