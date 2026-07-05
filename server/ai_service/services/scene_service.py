"""Scene segmentation service -- TransNetV2.

Processes video: extracts 1fps frames, runs TransNetV2, returns scene list.
"""

from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any
from typing import Any, Optional
import numpy as np
from configs import scene as scene_cfg

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

logger = logging.getLogger(__name__)

_transnet_model = None


def _load_transnet():
    global _transnet_model
    if _transnet_model is not None:
        return _transnet_model

    import torch
    import torch.nn  # noqa: F401
    from transnetv2_pytorch import TransNetV2

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Loading TransNetV2 on %s ...", device)
    _transnet_model = TransNetV2()
    _transnet_model = _transnet_model.to(device)
    _transnet_model.eval()

    if device == "cuda":
        alloc = torch.cuda.memory_allocated() / 1073741824
        logger.info("TransNetV2 loaded. CUDA: %.2f GB", alloc)

    return _transnet_model


def detect_scenes(video_path: str | Path) -> list[dict[str, Any]]:
    """Detect scene boundaries using TransNetV2 (v1.0+ predict_video API).

    Returns:
        [{index, start_time, end_time, thumbnail_path?}, ...]
    """
    import torch
    import numpy as np

    model = _load_transnet()

    try:
        with torch.no_grad():
            _, preds_sim, _ = model.predict_video(str(video_path), quiet=True)
        video_fps = model.get_video_fps(str(video_path))
    except Exception as e:
        logger.warning("ffmpeg decode failed (%s: %s), falling back to OpenCV",
                       type(e).__name__, e)
        frames_np, video_fps = _extract_frames_opencv(video_path, model._input_size[:2])
        with torch.no_grad():
            _, preds_sim, _ = model.predict_frames(frames_np)

    total_predictions = len(preds_sim)
    if total_predictions > 0:
        duration = total_predictions / video_fps
    else:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        duration = total_frames / fps if fps > 0 else 0

    # Use raw similarity scores with configurable threshold
    preds_np = preds_sim.cpu().numpy().flatten()
    cut_indices = np.where(preds_np > scene_cfg.threshold)[0]

    # Build initial segments as (start_frame, end_frame)
    segments = []
    prev_frame = 0
    for cut in cut_indices:
        segments.append((prev_frame, cut))
        prev_frame = cut
    if total_predictions > 0:
        segments.append((prev_frame, total_predictions))

    # Merge short scenes (min_scene_len is in seconds, convert to frames)
    # Adaptive: cap min_scene_len at 10% of video duration for short videos
    effective_min_scene_len = min(scene_cfg.min_scene_len, duration * 0.1)
    min_frames = int(effective_min_scene_len * video_fps)
    if min_frames > 1 and segments:
        merged = [segments[0]]
        for seg in segments[1:]:
            prev_start, prev_end = merged[-1]
            curr_start, curr_end = seg
            curr_len = curr_end - curr_start
            if curr_len < min_frames:
                merged[-1] = (prev_start, curr_end)
            else:
                merged.append(seg)
        segments = merged

    # Convert segments to scene dicts
    scenes = []
    for idx, (start_frame, end_frame) in enumerate(segments):
        start_sec = start_frame / video_fps
        end_sec = end_frame / video_fps
        scenes.append({
            "index": idx,
            "start_time": float(start_sec),
            "end_time": float(end_sec),
            "thumbnail_time": float(start_sec),
        })

    logger.info(
        "TransNetV2: %s -> %d scenes (threshold=%.1f, min_scene_len=%ds)",
        Path(video_path).name, len(scenes),
        scene_cfg.threshold, scene_cfg.min_scene_len,
    )

    # Explicit GPU/CPU memory cleanup after each video to avoid OOM accumulation
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    return scenes


def _unload_transnet():
    global _transnet_model
    if _transnet_model is None:
        return
    import gc
    logger.info("Unloading TransNetV2 ...")
    _transnet_model = None
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def extract_thumbnail(video_path: str | Path, time_sec: float, output_path: str | Path | None = None, rotation: int | None = None) -> Optional[bytes]:
    """Extract a single frame as JPEG bytes at given timestamp.

    If output_path is provided, saves to disk and returns bytes anyway.
    Returns None on failure.
    """
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_idx = int(time_sec * fps) if fps > 0 else int(time_sec * 30)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    # Rotation correction (if needed) — apply before imencode
    if rotation is None:
        from utils.rotation import get_video_rotation
        rotation = get_video_rotation(video_path)
    if rotation:
        from utils.rotation import apply_rotation
        frame = apply_rotation(frame, rotation)
    ret2, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ret2:
        return None
    jpeg_bytes = buf.tobytes()
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(jpeg_bytes)
    return jpeg_bytes

def _extract_frames_opencv(
    video_path: str | Path,
    target_size: tuple[int, int],
) -> tuple[np.ndarray, float]:
    """Fallback: read & resize all frames via OpenCV when ffmpeg pipe fails.

    Args:
        video_path: Path to the video file.
        target_size: (height, width) to resize each frame to.

    Returns:
        (frames_array, fps)  — stacked uint8 RGB frames and video FPS.
    """
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frames: list[np.ndarray] = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # OpenCV resize takes (width, height), so reverse target_size
        resized = cv2.resize(rgb, (target_size[1], target_size[0]),
                             interpolation=cv2.INTER_LINEAR)
        frames.append(resized)
    cap.release()

    if not frames:
        raise RuntimeError(f"No frames extracted from: {video_path}")

    return np.stack(frames, axis=0).astype(np.uint8), fps
