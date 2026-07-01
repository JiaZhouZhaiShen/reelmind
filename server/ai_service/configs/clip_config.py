"""open-clip semantic search configuration."""
from __future__ import annotations
from configs.base import ModuleConfig


class ClipConfig(ModuleConfig):
    """Configuration for open-clip visual semantic search."""

    enabled: bool = True
    # CLIP model architecture
    model_name: str = "ViT-B-16"
    # Pretrained weights source (code uses laion2b_s34b_b88k weights)
    pretrained: str = "laion2b_s34b_b88k"
    # Device to run inference on
    device: str = "cuda"
    # Batch size for frame encoding
    batch_size: int = 32
    # Default top-k for semantic search
    default_top_k: int = 20
