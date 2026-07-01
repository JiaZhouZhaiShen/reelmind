"""ReelMind AI Module Configurations — 7 individual configs.

6 AI modules + 1 pipeline runner config.
All configs are auto-loaded and accessible via get_all() or individual imports.
"""
from __future__ import annotations

from configs.base import ModuleConfig
from configs.scene_config import SceneConfig
from configs.yolo_config import YoloConfig
from configs.ocr_config import OcrConfig
from configs.clip_config import ClipConfig
from configs.whisper_config import WhisperConfig
from configs.diarization_config import DiarizationConfig
from configs.pipeline_config import PipelineConfig

# Singleton instances (loaded once, mutable in-memory)
scene = SceneConfig()
yolo = YoloConfig()
ocr = OcrConfig()
clip = ClipConfig()
whisper = WhisperConfig()
diarization = DiarizationConfig()
pipeline = PipelineConfig()

_ALL = {
    "scene": scene, "yolo": yolo, "ocr": ocr,
    "clip": clip, "whisper": whisper, "diarization": diarization,
    "pipeline": pipeline,
}


def get_all() -> dict[str, ModuleConfig]:
    return dict(_ALL)


def get(name: str) -> ModuleConfig | None:
    return _ALL.get(name)


def load_all():
    """Load all configs from JSON files (called at startup)."""
    for name, cfg in _ALL.items():
        try:
            cfg.load()
        except Exception as e:
            import logging
            logging.getLogger("configs").warning("Failed to load config '%s': %s", name, e)


def to_dict_all() -> dict:
    """Serialize all configs to a single dict (for the /config API response)."""
    return {name: cfg.to_dict() for name, cfg in _ALL.items()}


def update_from_dict(data: dict):
    """Batch-update configs from a dict.

    Supports:
    - Module dicts ({"scene": {"enabled": true, ...}})
    - Legacy flat keys ({"transnet": True, "batchSize": 10, ...})
    """
    dispatch_map = {
        "transnet": "scene", "yolo": "yolo", "ocr": "ocr",
        "clip": "clip", "whisper": "whisper", "diarization": "diarization",
    }
    for old_key, module_name in dispatch_map.items():
        if old_key in data:
            if isinstance(data[old_key], dict):
                _ALL[module_name].from_dict(data[old_key])
            else:
                _ALL[module_name].enabled = bool(data[old_key])

    for name in _ALL:
        if name in data and isinstance(data[name], dict):
            _ALL[name].from_dict(data[name])

    pipeline_map = {
        "autoRun": "auto_run_enabled",
        "autoRunStartHour": "auto_run_start_hour",
        "autoRunEndHour": "auto_run_end_hour",
        "autoRunGpuThreshold": "auto_run_gpu_threshold",
        "autoRunCheckInterval": "auto_run_check_interval",
        "autoRunMaxVideos": "auto_run_max_videos",
       "batchSize": "batch_size",
        "batchLoop": "batch_loop",
       "template": "template",
        "maxFileSizeMb": "max_file_size_mb",
    }
    for old_key, new_attr in pipeline_map.items():
        if old_key in data:
            setattr(pipeline, new_attr, data[old_key])

    for cfg in _ALL.values():
        cfg.save()


load_all()
