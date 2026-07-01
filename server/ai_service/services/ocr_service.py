"""Scene OCR service -- PaddleOCR, lang=ch, use_gpu=True.

Extracts text from scene middle frame with confidence threshold 0.7.
"""

from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any
from configs import ocr as ocr_cfg

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

logger = logging.getLogger(__name__)

_ocr_instance = None
_ocr_load_failed = False


def _load_ocr():
    global _ocr_instance, _ocr_load_failed
    if _ocr_instance is not None:
        return _ocr_instance

    logger.info("Loading PaddleOCR (lang=%s, use_gpu=%s) ...", ocr_cfg.lang, ocr_cfg.use_gpu)
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        logger.error("PaddleOCR not installed")
        _ocr_load_failed = True
        return None
    try:
        import torch
        # PaddlePaddle 2.6.x is incompatible with CUDA 12.4 (memory corruption).
        # Fallback to CPU, which uses PaddlePaddle's CPU-only path and avoids
        # the `munmap_chunk(): invalid pointer` crash.
        if ocr_cfg.use_gpu:
            logger.warning("Config says use_gpu=true but PaddlePaddle 2.6.x is incompatible with CUDA 12.4, forcing CPU")
        use_gpu = False
        _ocr_instance = PaddleOCR(
            lang=ocr_cfg.lang,
            use_gpu=use_gpu,
            show_log=False,
            use_angle_cls=True,
        )
    except Exception as e:
        logger.error("PaddleOCR load failed: %s", e)
        _ocr_load_failed = True
        return None

    import torch
    if torch.cuda.is_available():
        alloc = torch.cuda.memory_allocated() / 1073741824
        logger.info("PaddleOCR loaded. CUDA: %.2f GB", alloc)

    return _ocr_instance


def ocr_scene_middle(video_path: str | Path, time_sec: float) -> list[dict[str, Any]]:
    """OCR on the scene middle frame.

    Returns:
        [{text: str, confidence: float, bbox: {x, y, w, h}}, ...]
    """
    ocr = _load_ocr()
    if ocr is None:
        logger.warning("OCR not available, skipping")
        return []
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_idx = int(time_sec * fps) if fps > 0 else int(time_sec * 30)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        return []

    # PaddleOCR takes BGR image directly
    result = ocr.ocr(frame, cls=False)

    texts = []
    if result and len(result) > 0 and result[0] is not None:
        h, w = frame.shape[:2]
        for line in result[0]:
            bbox_pts = line[0]  # [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            text_info = line[1]
            text = text_info[0]
            confidence = text_info[1]

            if confidence < ocr_cfg.confidence_threshold:
                continue

            x_coords = [pt[0] for pt in bbox_pts]
            y_coords = [pt[1] for pt in bbox_pts]
            texts.append({
                "text": text,
                "confidence": round(float(confidence), 4),
                "bbox": {
                    "x": round(min(x_coords), 1),
                    "y": round(min(y_coords), 1),
                    "w": round(max(x_coords) - min(x_coords), 1),
                    "h": round(max(y_coords) - min(y_coords), 1),
                },
            })

    return texts

def _unload_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        return
    import gc
    logger.info('Unloading PaddleOCR ...')
    _ocr_instance = None
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            alloc = torch.cuda.memory_allocated() / 1073741824
            logger.info('PaddleOCR unloaded. CUDA: %.2f GB', alloc)
    except Exception:
        pass
