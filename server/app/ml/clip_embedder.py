from pathlib import Path
from typing import Any

import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import torch
import cv2
import numpy as np

from ..config import settings

# ── OpenCLIP 模型名映射（兼容旧配置） ──────────────────────────────────────
# 用户在 settings.CLIP_MODEL 中仍可配置 "ViT-B/32" 等旧名
_MODEL_MAP: dict[str, tuple[str, str]] = {
    "ViT-B/32": ("ViT-B-32", "laion2b_s34b_b79k"),
    "ViT-B/16": ("ViT-B-16", "laion2b_s34b_b88k"),
    "ViT-L/14": ("ViT-L-14", "laion2b_s32b_b82k"),
    # 也支持直接写 OpenCLIP 名
    "ViT-B-32": ("ViT-B-32", "laion2b_s34b_b79k"),
    "ViT-B-16": ("ViT-B-16", "laion2b_s34b_b88k"),
    "ViT-L-14": ("ViT-L-14", "laion2b_s32b_b82k"),
    "ViT-H-14": ("ViT-H-14", "laion2b_s32b_b79k"),
}

_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_clip_device = None
_clip_model_name: str = ""


def _load_clip():
    """OpenCLIP 单例加载，返回 (model, preprocess, tokenizer, device, model_name)。"""
    global _clip_model, _clip_preprocess, _clip_tokenizer, _clip_device, _clip_model_name
    if _clip_model is not None:
        return _clip_model, _clip_preprocess, _clip_tokenizer, _clip_device, _clip_model_name

    import open_clip

    _clip_device = "cuda" if torch.cuda.is_available() else "cpu"
    raw_name = getattr(settings, "CLIP_MODEL", "ViT-B-16")
    entry = _MODEL_MAP.get(raw_name)
    if entry is not None:
        arch_name, pretrained = entry
    else:
        arch_name = raw_name
        pretrained = "openai"

    try:
        _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
            arch_name, pretrained=pretrained
        )
        _clip_tokenizer = open_clip.get_tokenizer(arch_name)
    except ImportError:
        return None, None, None, None, ""

    _clip_model = _clip_model.to(_clip_device)
    _clip_model.eval()
    _clip_model_name = arch_name
    return _clip_model, _clip_preprocess, _clip_tokenizer, _clip_device, _clip_model_name


def _frame_embedding(frame_rgb: np.ndarray) -> torch.Tensor:
    """单帧 → L2 归一化 embedding。"""
    model, preprocess, _, device, _ = _load_clip()
    if model is None:
        return torch.empty(0)
    image_input = preprocess(frame_rgb).unsqueeze(0).to(device)
    with torch.no_grad(), torch.cuda.amp.autocast(enabled=device == "cuda"):
        emb = model.encode_image(image_input)
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb[0].cpu()


def get_video_embedding(video_path: str | Path, time_sec: float | None = None) -> list[float] | None:
    """提取视频（的指定时间帧或 8 帧平均）的 CLIP embedding。"""
    if not settings.ENABLE_CLIP:
        return None

    model, _, _, _, _ = _load_clip()
    if model is None:
        return None

    cap = cv2.VideoCapture(str(video_path))
    frames = []
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return None

    if time_sec is not None:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps > 0:
            frame_idx = int(time_sec * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return None
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            embedding = _frame_embedding(frame_rgb)
            return embedding.tolist()
        cap.release()
        return None

    # 无时间戳时采样 8 帧取平均
    sample_indices = [int(total_frames * i / 8) for i in range(1, 9)]
    for idx in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(frame_rgb)
    cap.release()

    if not frames:
        return None

    embeddings = [_frame_embedding(f) for f in frames]
    embeddings = [e for e in embeddings if e.numel() > 0]
    if not embeddings:
        return None
    avg_embedding = torch.stack(embeddings).mean(dim=0).cpu().numpy()
    return avg_embedding.tolist()


def get_text_embedding(text: str) -> list[float] | None:
    """文本 → L2 归一化 CLIP embedding。"""
    if not settings.ENABLE_CLIP:
        return None

    model, _, tokenizer, device, _ = _load_clip()
    if model is None:
        return None

    inputs = tokenizer([text]).to(device)
    with torch.no_grad(), torch.cuda.amp.autocast(enabled=device == "cuda"):
        text_embeds = model.encode_text(inputs)
        text_embeds = text_embeds / text_embeds.norm(dim=-1, keepdim=True)
    return text_embeds[0].cpu().tolist()
