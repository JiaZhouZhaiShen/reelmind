"""Semantic visual search -- OpenCLIP ViT-B-16 + laion2b.

Interfaces:
  - encode_frames(video_path, timestamps)  batch encode frames
  - search(text, top_k=20)                 cosine similarity search
  - compute_embedding_for_search(text)     compute text embedding
"""

from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any
from configs import clip as clip_cfg

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

logger = logging.getLogger(__name__)

_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_clip_device = None
_clip_load_failed = False



def _load_clip():
    global _clip_model, _clip_preprocess, _clip_tokenizer, _clip_device, _clip_load_failed
    if _clip_model is not None:
        return _clip_model, _clip_preprocess, _clip_tokenizer, _clip_device
    import torch
    import open_clip

    _clip_device = "cuda" if torch.cuda.is_available() else "cpu"

    logger.info("Loading OpenCLIP %s + %s on %s ...", clip_cfg.model_name, clip_cfg.pretrained, _clip_device)
    try:
        _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
            clip_cfg.model_name,
            pretrained=clip_cfg.pretrained,
        )
        _clip_tokenizer = open_clip.get_tokenizer(clip_cfg.model_name)

        _clip_model = _clip_model.to(_clip_device)
        _clip_model.eval()
    except Exception as e:
        logger.error("CLIP model load failed (cannot download weights): %s", e)
        _clip_load_failed = True
        return None, None, None, None

    if _clip_device == "cuda":
        alloc = torch.cuda.memory_allocated() / 1073741824
        logger.info("CLIP model loaded. CUDA: %.2f GB", alloc)

    return _clip_model, _clip_preprocess, _clip_tokenizer, _clip_device


def encode_frames(video_path: str | Path, frame_timestamps: list) -> list[dict]:
    import cv2
    import numpy as np
    import torch
    from PIL import Image

    model, preprocess, _, device = _load_clip()
    if model is None:
        logger.warning("CLIP model not loaded, returning empty results")
        return []
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)

    images = []
    valid_ts = []
    try:
        for t in frame_timestamps:
            frame_idx = int(t * fps) if fps > 0 else int(t * 30)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_pil = Image.fromarray(frame_rgb)
            preprocessed = preprocess(frame_pil)  # [C, H, W], no batch dim
            images.append(preprocessed)
            valid_ts.append(t)
    finally:
        cap.release()

    if not images:
        return []

    # ── Batch encode all frames in one forward pass ──
    batch = torch.stack(images).to(device)
    with torch.no_grad(), torch.cuda.amp.autocast(enabled=(device == "cuda")):
        embs = model.encode_image(batch)
        embs = embs / embs.norm(dim=-1, keepdim=True)

    results = []
    for t, emb in zip(valid_ts, embs):
        results.append({
            "time_sec": t,
            "embedding": emb.cpu().numpy().astype(np.float32).tobytes(),
        })

    logger.info("Batch encoded %d frames from %s", len(results), Path(video_path).name)
    return results


def search(query: str, top_k: int | None = None) -> list[dict]:
    if top_k is None:
        top_k = clip_cfg.default_top_k
    import numpy as np
    from models.ai_models import Frame, get_ai_session

    model, _, tokenizer, device = _load_clip()

    inputs = tokenizer([query]).to(device)
    import torch
    with torch.no_grad(), torch.cuda.amp.autocast(enabled=(device == "cuda")):
        text_embeds = model.encode_text(inputs)
        text_embeds = text_embeds / text_embeds.norm(dim=-1, keepdim=True)
    query_vec = text_embeds[0].cpu().numpy().astype(np.float32)

    session = get_ai_session()
    try:
        all_frames = session.query(Frame).filter(Frame.embedding.isnot(None)).all()
        results = []
        for f in all_frames:
            blob = f.embedding
            if blob is None:
                continue
            vec = np.frombuffer(blob, dtype=np.float32)
            sim = float(np.dot(query_vec, vec))
            results.append({
                "frame_id": f.id,
                "video_id": f.video_id,
                "time_sec": f.time_sec,
                "frame_path": f.frame_path or "",
                "score": round(float(sim), 4),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
    finally:
        session.close()


def compute_embedding_for_search(query_text: str):
    import numpy as np
    import torch

    model, _, tokenizer, device = _load_clip()
    inputs = tokenizer([query_text]).to(device)
    with torch.no_grad(), torch.cuda.amp.autocast(enabled=(device == "cuda")):
        text_embeds = model.encode_text(inputs)
        text_embeds = text_embeds / text_embeds.norm(dim=-1, keepdim=True)
    return text_embeds[0].cpu().numpy().astype(np.float32).tolist()

def _unload_clip():
    global _clip_model, _clip_preprocess, _clip_tokenizer, _clip_device
    if _clip_model is None:
        return
    import gc
    logger.info('Unloading CLIP ...')
    _clip_model = None
    _clip_preprocess = None
    _clip_tokenizer = None
    _clip_device = None
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            alloc = torch.cuda.memory_allocated() / 1073741824
            logger.info('CLIP unloaded. CUDA: %.2f GB', alloc)
    except Exception:
        pass

