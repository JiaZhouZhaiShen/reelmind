"""AI Pipeline Templates — predefined step combinations.

Each template defines which AI modules are enabled/disabled.
Templates are loaded on demand and can be applied at runtime.
"""
from __future__ import annotations

from configs import scene, yolo, ocr, clip, whisper, diarization, pipeline

TEMPLATES: dict[str, dict[str, bool]] = {
    "full": {
        "label": "完整处理",
        "description": "全部 AI 模块：场景检测 + YOLO + OCR + Whisper + CLIP",
        "scene": True, "yolo": True, "ocr": False,
       "whisper": True, "clip": True, "diarization": False,
    },
    "quick_index": {
        "label": "快速索引",
        "description": "场景检测 + YOLO + CLIP，适合带物体标签的快速入库",
        "scene": True, "yolo": True, "ocr": False,
        "whisper": False, "clip": True, "diarization": False,
    },
    "subtitle_only": {
        "label": "字幕版",
        "description": "仅 Whisper 语音转文字，适合采访/对话类视频",
        "scene": False, "yolo": False, "ocr": False,
        "whisper": True, "clip": False, "diarization": False,
    },
}


def get_templates() -> dict[str, dict]:
    """Return all templates with metadata."""
    result = {}
    for key, tmpl in TEMPLATES.items():
        result[key] = {
            "label": tmpl["label"],
            "description": tmpl["description"],
            "enabled": {k: v for k, v in tmpl.items() if k not in ("label", "description")},
        }
    return result


def apply_template(name: str) -> dict:
    """Apply a template by updating module configs."""
    if name not in TEMPLATES:
        raise ValueError(f"Unknown template: {name}")
    tmpl = TEMPLATES[name]
    enabled = {k: v for k, v in tmpl.items() if k not in ("label", "description")}

    # Map short names to config objects
    module_map = {
        "scene": scene, "yolo": yolo, "ocr": ocr,
        "clip": clip, "whisper": whisper, "diarization": diarization,
    }
    for mod_name, mod_cfg in module_map.items():
        if mod_name in enabled:
            mod_cfg.enabled = enabled[mod_name]
            mod_cfg.save()

    # Save template name in pipeline config
    pipeline.template = name
    pipeline.save()

    return {
        "status": "ok",
        "template": name,
        "enabled": enabled,
    }
