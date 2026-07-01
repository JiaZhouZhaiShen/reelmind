"""faster-whisper speech-to-text configuration."""
from __future__ import annotations
from configs.base import ModuleConfig


class WhisperConfig(ModuleConfig):
    """Configuration for faster-whisper transcription."""

    enabled: bool = True
    # Model size (tiny, base, small, medium, large-v3) — medium recommended for 8GB VRAM
    model_size: str = "tiny"
    # Device to run inference on
    device: str = "cuda"
    # Compute type (float16, int8_float16, etc.)
    compute_type: str = "float16"
    # Source language (auto-detect if empty)
    language: str = "zh"
    # Beam size for decoding
    beam_size: int = 3
    # VAD filter (filter out non-speech segments)
    vad_filter: bool = True
    # Minimum silence duration in ms
    min_silence_duration_ms: int = 300
