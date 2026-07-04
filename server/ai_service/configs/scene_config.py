"""TransNetV2 scene detection configuration."""
from __future__ import annotations
from configs.base import ModuleConfig


class SceneConfig(ModuleConfig):
    """Configuration for TransNetV2 scene detection."""

    enabled: bool = True
    # Scene change detection threshold (0.0 to 1.0, higher = fewer cuts)
    # 0.5 recommended: only hard cuts, fewer scenes = less YOLO/OCR/CLIP load
    threshold: float = 0.5
    # Minimum scene length in seconds (shorter scenes merged into previous)
    # 60 recommended for 2W+ videos: cuts total scenes by 50-70%
    min_scene_len: float = 2.5
    # Device to run inference on
    device: str = "cuda"
