"""pyannote speaker diarization configuration."""
from __future__ import annotations
from typing import Optional
from configs.base import ModuleConfig


class DiarizationConfig(ModuleConfig):
    """Configuration for pyannote speaker diarization."""

    enabled: bool = True
    # Pretrained pipeline name on HuggingFace
    pipeline_name: str = "pyannote/speaker-diarization-3.1"
    # Device to run inference on
    device: str = "cuda"
    # Number of speakers (None = auto-detect)
    num_speakers: int | None = None
    # Min speakers for clustering
    min_speakers: int | None = None
    # Max speakers for clustering
    max_speakers: int | None = None
    # Agglomerative clustering threshold
    cluster_threshold: float = 0.5
