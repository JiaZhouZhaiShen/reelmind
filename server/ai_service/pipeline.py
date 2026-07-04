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
                    DO UPDATE SET status = :st2, completed_at = NOW(), 
                       error_message = CASE WHEN :st2 = 'completed' THEN NULL ELSE ai_engine_jobs.error_message END"""),
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

def _timeout_run(func, *args, timeout_seconds=300):
    """Run func(*args) with a timeout. Raises TimeoutError on timeout.

    Creates a fresh ThreadPoolExecutor per call (acceptable because calls
    are long-running seconds-level operations).
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutTE
    with ThreadPoolExecutor(max_workers=1) as _ex:
        _f = _ex.submit(func, *args)
        try:
            return _f.result(timeout=timeout_seconds)
        except _FutTE:
            raise TimeoutError(f"timed out after {timeout_seconds}s")

def get_pipeline_steps() -> dict:
    """Return full config as dict (backward-compatible with /config API)."""
    from configs import to_dict_all
    return to_dict_all()

def set_pipeline_steps(config: dict):
    """Update config from dict (backward-compatible with POST /config)."""
    from configs import update_from_dict
    update_from_dict(config)

def _get_engine_jobs(media_id: str) -> dict[str, str]:
    """Query ai_engine_jobs for a media and return {engine_name: status}."""
    from models.db import get_pg_session
    from sqlalchemy import text
    jobs = {}
    try:
        s = get_pg_session()
        try:
            rows = s.execute(
                text("SELECT engine_name, status FROM ai_engine_jobs WHERE media_id = :mid"),
                {"mid": media_id},
            ).fetchall()
            for row in rows:
                jobs[row[0]] = row[1]
        finally:
            s.close()
    except Exception as e:
        logger.warning("Failed to query engine jobs for %s: %s", media_id, e)
    return jobs

class AIPipeline:
    """Manages the end-to-end AI processing sequence for a video."""

    def __init__(self, video_id: str, video_path: str, progress_callback: Callable | None = None, engines: list[str] | None = None):
        self.video_id = video_id
        self.video_path = video_path
        self.progress_callback = progress_callback or (lambda msg, pct: None)
        self._session = None
        self.engines = engines

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

            # Check which engines are already completed (avoid re-processing)
            engine_statuses = _get_engine_jobs(self.video_id)

            # ── Step 1: Scene cut (TransNetV2) ──
            if engine_statuses.get("scene") == "completed":
                self._progress("Scene detection already completed, loading existing scenes", 15)
                existing_scenes = session.query(Scene).filter(
                    Scene.video_id == self.video_id
                ).order_by(Scene.scene_index).all()
                scene_records = list(existing_scenes)
                self._progress(f"Loaded {len(scene_records)} existing scenes", 20)
            elif (self.engines is None or "scene" in self.engines) and scene_cfg.enabled:
                self._progress("Scene detection (TransNetV2)...", 5)
                _update_model_state("transnet", True)
                from services.scene_service import detect_scenes, extract_thumbnail
                scenes_data = detect_scenes(str(video_path))
                self._progress(f"Found {len(scenes_data)} scenes", 15)

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
            else:
                self._progress("Scene detection skipped", 15)
                scenes_data = []

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
                session.commit()
                self._progress("Using single full-video scene", 20)

            total_scenes = len(scene_records)
            enabled_steps = []
            if (self.engines is None or "yolo" in self.engines) and yolo_cfg.enabled: enabled_steps.append("yolo")
            if (self.engines is None or "ocr" in self.engines) and ocr_cfg.enabled: enabled_steps.append("ocr")
            if (self.engines is None or "clip" in self.engines) and clip_cfg.enabled: enabled_steps.append("clip")
            step_count = len(enabled_steps) or 1

            # ── Step 2: YOLO batch ──
            if engine_statuses.get("yolo") == "completed":
                self._progress("YOLO already completed, skipping", 20)
            elif (self.engines is None or "yolo" in self.engines) and yolo_cfg.enabled:
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
            if engine_statuses.get("ocr") == "completed":
                self._progress("OCR already completed, skipping", 20)
            elif (self.engines is None or "ocr" in self.engines) and ocr_cfg.enabled:
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
            if engine_statuses.get("clip") == "completed":
                self._progress("CLIP already completed, skipping", 40)
                _clip_ok = True
            elif (self.engines is None or "clip" in self.engines) and clip_cfg.enabled:
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

            # ── Step 5a: Whisper transcription ──
            subtitles_data = []
            if engine_statuses.get("transcript") == "completed":
                self._progress("Transcription already completed, loading existing subtitles", 80)
                existing_subs = session.query(Subtitle).filter(
                    Subtitle.video_id == self.video_id
                ).order_by(Subtitle.start).all()
                subtitles_data = [{"start": s.start, "end": s.end, "text": s.text, "language": s.language} for s in existing_subs]
                if subtitles_data:
                    self._progress(f"Loaded {len(subtitles_data)} subtitle segments", 87)
            elif (self.engines is None or "transcript" in self.engines) and whisper_cfg.enabled:
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
                    else:
                        self._progress("No speech detected", 87)
            else:
                self._progress("Transcription skipped", 80)

            # ── Step 5b: Speaker diarization ──
            if engine_statuses.get("diarization") == "completed":
                self._progress("Diarization already completed, skipping", 95)
            elif (self.engines is None or "diarization" in self.engines) and diarization_cfg.enabled and subtitles_data:
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
            elif subtitles_data:
                self._progress("Speaker diarization skipped", 93)

            # ── Update ai_engine_jobs status ──
            if (self.engines is None or "scene" in self.engines) and scene_cfg.enabled and engine_statuses.get("scene") != "completed":
                _set_job_status(self.video_id, "scene", "completed")
            if whisper_cfg.enabled and os.environ.get('ENABLE_WHISPER', 'false') == 'true' and engine_statuses.get("transcript") != "completed":
                _set_job_status(self.video_id, "transcript", "completed")
            if clip_cfg.enabled and os.environ.get('ENABLE_CLIP', 'false') == 'true' and _clip_ok and engine_statuses.get("clip") != "completed":
                _set_job_status(self.video_id, "clip", "completed")
            if diarization_cfg.enabled and subtitles_data and engine_statuses.get("diarization") != "completed":
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
    failed_video_ids: set[str] = set()

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
                    # Wrap OpenCV video metadata reading with timeout (30s)
                    def _read_video_meta(vp: str):
                        cap = _cv2.VideoCapture(vp)
                        try:
                            fps = cap.get(_cv2.CAP_PROP_FPS)
                            tf = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
                            dur = tf / fps if fps > 0 else 0
                            w = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
                            h = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
                            return dur, fps, tf, w, h
                        finally:
                            cap.release()
                    dur, fps, tf, w, h = _timeout_run(_read_video_meta, vp, timeout_seconds=300)
                    video = _AIVideo(id=str(asset.id), file_path=vp, file_name=asset.file_name or _Path(vp).name,
                        duration=float(dur or 0), width=w, height=h, fps=float(fps or 0))
                    ai_s.add(video)
                    ai_s.flush()
                    scenes_data = json.loads(subprocess.run([sys.executable, '/app/services/scene_worker.py', vp], capture_output=True, text=True, timeout=600, cwd='/app').stdout)
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
                    _set_job_status(str(asset.id), "scene", "error")
                    failed_video_ids.add(str(asset.id))
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
    else:
        _cb("Step 1/5: TransNetV2 skipped", 20)

    # Cascade scene failures to downstream engines (Scene → YOLO/OCR/CLIP)
    if failed_video_ids:
        _scene_downstream = []
        if (engines is None or "yolo" in engines) and yolo_cfg.enabled:
            _scene_downstream.append("yolo")
        if (engines is None or "ocr" in engines) and ocr_cfg.enabled:
            _scene_downstream.append("ocr")
        if (engines is None or "clip" in engines) and clip_cfg.enabled:
            _scene_downstream.append("clip")
        if _scene_downstream:
            for _vid in failed_video_ids:
                for _eng in _scene_downstream:
                    _set_job_status(_vid, _eng, "error")
            logger.info(
                "Cascade: scene failure → %s error for %d videos",
                _scene_downstream, len(failed_video_ids),
            )

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
        _yolo_failed_videos: set[str] = set()
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
                    if scene.video_id in _yolo_failed_videos:
                        continue
                    try:
                        video = ai_s.query(_AIVideo).filter(_AIVideo.id == scene.video_id).first()
                        if not video: continue
                        objects = _timeout_run(
                            _detect_objects, video.file_path, scene.start_time, scene.end_time,
                            timeout_seconds=30,
                        )
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
                        _yolo_failed_videos.add(scene.video_id)
                        _set_job_status(str(scene.video_id), "yolo", "error")
                        failed_video_ids.add(str(scene.video_id))
                        if isinstance(e, TimeoutError):
                            logger.warning(
                                "YOLO timeout for scene %s (video %s), skip remaining scenes",
                                scene.id, scene.video_id,
                            )
                        else:
                            logger.error("YOLO failed for scene %s: %s", scene.id, e)
                ai_s.close()
            finally:
               if "yolo" not in _pre_loaded_models:
                   _unload_yolo()
               if "yolo" not in _pre_loaded_models: _update_model_state("yolo", False)
        # ── Mark YOLO completed for videos that finished processing ──
        if scenes_no_tag:
            _yolo_done_vids = set(sc.video_id for sc in scenes_no_tag)
            for _vid in _yolo_done_vids:
                if _vid not in _yolo_failed_videos:
                    _set_job_status(_vid, "yolo", "completed")
        _cb("Step 2/5: YOLO done", 40)
        if _yolo_failed_videos:
            logger.info("YOLO: %d videos failed, marked error", len(_yolo_failed_videos))

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
        _ocr_failed_videos: set[str] = set()
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
                    if scene.video_id in _ocr_failed_videos:
                        continue
                    try:
                        video = ai_s.query(_AIVideo).filter(_AIVideo.id == scene.video_id).first()
                        if not video: continue
                        mid_time = (scene.start_time + scene.end_time) / 2
                        ocr_results = _timeout_run(
                            _ocr_scene, video.file_path, mid_time,
                            timeout_seconds=30,
                        )
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
                        _ocr_failed_videos.add(scene.video_id)
                        _set_job_status(str(scene.video_id), "ocr", "error")
                        failed_video_ids.add(str(scene.video_id))
                        if isinstance(e, TimeoutError):
                            logger.warning(
                                "OCR timeout for scene %s (video %s), skip remaining scenes",
                                scene.id, scene.video_id,
                            )
                        else:
                            logger.error("OCR failed for scene %s: %s", scene.id, e)
                ai_s.close()
            finally:
               if "ocr" not in _pre_loaded_models:
                   _unload_ocr()
               if "ocr" not in _pre_loaded_models: _update_model_state("ocr", False)
        # ── Mark OCR completed for videos that finished processing ──
        if scenes_no_ocr:
            _ocr_done_vids = set(sc.video_id for sc in scenes_no_ocr)
            for _vid in _ocr_done_vids:
                if _vid not in _ocr_failed_videos:
                    _set_job_status(_vid, "ocr", "completed")
        _cb("Step 3/5: OCR done", 60)
        if _ocr_failed_videos:
            logger.info("OCR: %d videos failed, marked error", len(_ocr_failed_videos))

    else:
        _cb("Step 3/5: OCR skipped", 60)

    # ══════════════════════════════════════════
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
            _clip_failed_videos: set[str] = set()
            try:
                vid_scenes: dict = {}
                for sc in scenes_no_frame: vid_scenes.setdefault(sc.video_id, []).append(sc)
                for vdx, (vid, sc_list) in enumerate(vid_scenes.items()):
                    if cancel_event and cancel_event.is_set():
                        _cb("Cancelled during CLIP step", 60)
                        break
                    ai_s = get_ai_session()
                    video = ai_s.query(_AIVideo).filter(_AIVideo.id == vid).first()
                    ai_s.close()
                    if not video:
                        continue
                    for sdx, scene in enumerate(sc_list):
                        if cancel_event and cancel_event.is_set():
                            break
                        if vid in _clip_failed_videos:
                            break
                        try:
                            mid_time = (scene.start_time + scene.end_time) / 2
                            embs = _timeout_run(
                                _encode_frames, video.file_path, [mid_time],
                                timeout_seconds=30,
                            )
                            ai_s = get_ai_session()
                            if embs:
                                ai_s.add(_Frame(video_id=vid, scene_id=scene.id,
                                    time_sec=embs[0]["time_sec"], embedding=embs[0]["embedding"]))
                            ai_s.commit(); ai_s.close()
                            _cb(f"CLIP [{vdx+1}/{len(vid_scenes)}] video {vid} scene {sdx+1}/{len(sc_list)}",
                                60 + (vdx + 1) / len(vid_scenes) * 20)
                        except Exception as e:
                            try:
                                ai_s.rollback()
                                ai_s.close()
                            except Exception:
                                 pass
                            _clip_failed_videos.add(vid)
                            _set_job_status(str(vid), "clip", "error")
                            failed_video_ids.add(str(vid))
                            if isinstance(e, TimeoutError):
                                logger.warning(
                                    "CLIP timeout for scene %s (video %s), skip remaining scenes",
                                    scene.id, vid,
                                )
                            else:
                                logger.error("CLIP failed for scene %s (video %s): %s", scene.id, vid, e)
                # ── Mark CLIP completed for videos that finished processing ──
                _clip_done_vids = set(vid_scenes.keys())
                for _vid in _clip_done_vids:
                    if _vid not in _clip_failed_videos:
                        _set_job_status(_vid, "clip", "completed")
                _cb("Step 4/5: CLIP done", 80)
                if _clip_failed_videos:
                    logger.info("CLIP: %d videos failed, marked error", len(_clip_failed_videos))
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
                        _set_job_status(str(asset.id), "transcript", "error")
                        if (engines is None or "diarization" in engines) and diarization_cfg.enabled:
                            _set_job_status(str(asset.id), "diarization", "error")
                        failed_video_ids.add(str(asset.id))
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
    step_results["completed"] = len(pending_assets) - len(failed_video_ids) - step_results["skipped"]
    if step_results["completed"] < 0:
        step_results["completed"] = 0
    _cb("Batch pipeline complete!", 100)
    logger.info("Batch pipeline done: %d completed, %d failed, %d skipped",
        step_results["completed"], step_results["failed"], step_results["skipped"])
    return step_results


