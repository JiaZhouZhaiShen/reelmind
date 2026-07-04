"""Object detection / auto-tagging -- YOLOv8n.

For each scene, sample head/mid/tail frames, merge objects appearing 2+ times.
"""

from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any
from configs import yolo as yolo_cfg

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["ULTRALYTICS_CACHE_DIR"] = os.environ.get("MODEL_ROOT", "/tmp") + "/ultralytics"

logger = logging.getLogger(__name__)
_yolo_load_failed = False
_yolo_model = None


def _load_yolo():
    global _yolo_model, _yolo_load_failed
    if _yolo_model is not None:
        return _yolo_model

    from ultralytics import YOLO
    # Use writable MODEL_ROOT for model cache
    model_root = os.environ.get("MODEL_ROOT", os.environ.get("CACHE_ROOT", "/tmp"))
    model_dir = os.path.join(model_root, "ultralytics")
    model_path = os.path.join(model_dir, "yolov8n.pt")
    os.makedirs(model_dir, exist_ok=True)

    # Try loading from disk first (cached)
    if os.path.isfile(model_path):
        try:
            _yolo_model = YOLO(model_path)
        except Exception as e:
            logger.warning("YOLO cached model load failed: %s", e)
            _yolo_model = None

    # Download if not cached yet
    if _yolo_model is None:
        try:
            _yolo_model = YOLO(yolo_cfg.model_name)
        except Exception as e:
            logger.warning("YOLOv8n GitHub download failed: %s", e)
            # Try huggingface mirror
            try:
                hf_url = "https://hf-mirror.com/ultralytics/yolov8/resolve/main/yolov8n.pt"
                logger.info("Downloading YOLOv8n from HF mirror: %s", hf_url)
                import urllib.request as _ur
                _ur.urlretrieve(hf_url, model_path)
                _yolo_model = YOLO(model_path)
            except Exception as e2:
                logger.error("YOLO load failed (both GitHub and HF mirror): %s, %s", e, e2)
                _yolo_load_failed = True
                return None

    # Cache the model file for next time
    if os.path.isfile("yolov8n.pt") and not os.path.isfile(model_path):
        try:
            import shutil
            shutil.copy2("yolov8n.pt", model_path)
        except Exception:
            pass

    import numpy as np
    _yolo_model(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False)

    import torch
    if torch.cuda.is_available():
        alloc = torch.cuda.memory_allocated() / 1073741824
        logger.info("YOLOv8n loaded. CUDA: %.2f GB", alloc)

    return _yolo_model



def detect_scene_objects(video_path: str | Path, start_time: float, end_time: float, rotation: int | None = None) -> list[dict[str, Any]]:
    """Detect objects in a scene by sampling 3 frames.

    Returns:
        [{label: str, confidence: float, count: int}, ...]
    """
    model = _load_yolo()
    if model is None:
        logger.warning("YOLO not available")
        return []
    import cv2
    import numpy as np

    duration = end_time - start_time
    if duration <= 0:
        logger.warning("YOLO: zero/negative scene duration (%.3f), skipping", duration)
        return []
    sample_times = [
        start_time,
        start_time + duration / 2,
        end_time - max(1.0, duration / 4),
    ]

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning("YOLO: cannot open video %s", video_path)
        return []
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
    object_counts = {}

    frames_batch = []
    # Rotation detection (once, applied per frame before resize)
    if rotation is None:
        from utils.rotation import get_video_rotation
        rotation = get_video_rotation(video_path)
    if rotation:
        from utils.rotation import apply_rotation as _apply_yolo_rotation
    try:
        for t in sample_times:
            if t < 0:
                continue
            frame_idx = int(t * fps)
            if total_frames > 0 and frame_idx >= total_frames:
                frame_idx = total_frames - 1
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx))
            ret, frame = cap.read()
            if not ret:
               continue
            # ⚠ Rotation must be applied BEFORE cv2.resize() — resize to 640×640 after rotation loses orientation
            if rotation:
                frame = _apply_yolo_rotation(frame, rotation)
            if frame.shape[0] == 0 or frame.shape[1] == 0:
                logger.warning("YOLO: zero-dim frame at time %.2f, skipping", t)
                continue
            # Normalize frame: ensure 3-channel BGR, valid dims
            if len(frame.shape) < 3:
                continue
            h, w = frame.shape[:2]
            # Pre-resize to 640x640 to avoid YOLO internal letterbox issues
            if w < 32 or h < 32:
                logger.warning("YOLO: tiny frame %dx%d at time %.2f, skipping", w, h, t)
                continue
            frame = cv2.resize(frame, (640, 640))
            frames_batch.append(frame)

        if not frames_batch:
            logger.warning("YOLO: no valid frames sampled for scene [%.2f, %.2f]", start_time, end_time)
            return []

        # Pass as a list of individual (640,640,3) arrays so YOLO's internal
        # letterbox always receives clean HWC frames.
        batch = [np.ascontiguousarray(f) for f in frames_batch]
        try:
            results = model(batch, verbose=False, conf=yolo_cfg.confidence_threshold, iou=yolo_cfg.iou_threshold, max_det=yolo_cfg.max_detections)
        except Exception as yolo_e:
            logger.warning("YOLO model inference failed: %s", yolo_e)
            return []

        for result in results:
            if result is None or result.boxes is None or result.boxes.cls is None:
                continue
            class_ids = result.boxes.cls.cpu().numpy().astype(int)
            confs = result.boxes.conf.cpu().numpy()
            names = result.names

            for cid, conf in zip(class_ids, confs):
                label = names.get(int(cid), f"class_{cid}")
                if label not in object_counts:
                    object_counts[label] = {"count": 0, "conf_sum": 0.0}
                object_counts[label]["count"] += 1
                object_counts[label]["conf_sum"] += float(conf)
    finally:
        cap.release()

    # Filter: only keep objects appearing 2+ times across samples
    result = []
    for label, data in object_counts.items():
        if data["count"] >= 2:
            result.append({
                "label": label,
                "confidence": round(data["conf_sum"] / data["count"], 4),
                "count": data["count"],
            })

    result.sort(key=lambda x: x["count"], reverse=True)
    return result


def _unload_yolo():
    global _yolo_model
    if _yolo_model is None:
        return
    import gc
    logger.info('Unloading YOLOv8n ...')
    _yolo_model = None
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
