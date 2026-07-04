"""Three independent pipeline config managers - manual, auto, single.

Rule 7: Configuration as Code - defaults in code, JSON is persistence layer.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/data/reelmind/data"))
_CONFIG_DIR = DATA_ROOT / "configs"

_DEFAULT_MANUAL = {
    "enabled": True,
    "engines": ["scene", "yolo", "ocr", "clip", "transcript", "diarization"],
    "batch_size": 100,
    "timeout_minutes": 180,
    "filters": {
        "max_file_size_mb": 2000,
        "max_duration_minutes": 30,
    },
}

_DEFAULT_AUTO = {
    "enabled": False,
    "engines": ["scene", "yolo", "ocr", "clip", "transcript", "diarization"],
    "batch_size": 50,
    "time_window_start": 0,
    "time_window_end": 6,
    "gpu_threshold_percent": 50,
    "check_interval_seconds": 60,
    "filters": {
        "max_file_size_mb": 10000,
        "max_duration_minutes": 60,
    },
}

_DEFAULT_SINGLE = {
    "enabled": True,
    "engines": ["scene", "yolo", "ocr", "clip", "transcript", "diarization"],
    "timeout_minutes": 60,
    "filters": {
        "max_file_size_mb": 0,
        "max_duration_minutes": 0,
    },
}

_CONFIGS = {
    "manual": (_DEFAULT_MANUAL, "manual_pipeline.json"),
    "auto": (_DEFAULT_AUTO, "auto_pipeline.json"),
    "single": (_DEFAULT_SINGLE, "single_pipeline.json"),
}


def _read_config(name: str) -> dict[str, Any]:
    defaults, filename = _CONFIGS[name]
    path = _CONFIG_DIR / filename
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = _deep_merge(defaults, data)
            return merged
        else:
            _write_config(name, defaults)
            return dict(defaults)
    except Exception as e:
        logger.warning("Failed to read %s config: %s, using defaults", name, e)
        return dict(defaults)


def _write_config(name: str, cfg: dict) -> None:
    _, filename = _CONFIGS[name]
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = _CONFIG_DIR / filename
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        logger.info("Saved %s config to %s", name, path)
    except Exception as e:
        logger.error("Failed to save %s config: %s", name, e)


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    result = dict(defaults)
    for key, val in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def get_manual_config() -> dict[str, Any]:
    return _read_config("manual")

def save_manual_config(cfg: dict) -> None:
    merged = _deep_merge(_DEFAULT_MANUAL, cfg)
    _write_config("manual", merged)

def get_auto_config() -> dict[str, Any]:
    """Read auto config from PG (primary), fallback to JSON file."""
    try:
        from app.database import sync_session_factory
        from app.models.pipeline_config import PipelineConfig
        session = sync_session_factory()
        try:
            pg_config = session.query(PipelineConfig).filter(PipelineConfig.name == "auto").first()
            if pg_config and pg_config.config:
                merged = _deep_merge(_DEFAULT_AUTO, pg_config.config)
                return merged
        finally:
            session.close()
    except Exception as e:
        logger.warning("Failed to read auto config from PG: %s, falling back to JSON", e)
    return _read_config("auto")

def save_auto_config(cfg: dict) -> None:
    merged = _deep_merge(_DEFAULT_AUTO, cfg)
    # Write to PG (primary)
    try:
        from app.database import sync_session_factory
        from app.models.pipeline_config import PipelineConfig
        session = sync_session_factory()
        try:
            pg_config = session.query(PipelineConfig).filter(PipelineConfig.name == "auto").first()
            if pg_config:
                pg_config.config = merged
            else:
                session.add(PipelineConfig(name="auto", config=merged))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to save auto config to PG: %s", e)
    # Write to JSON file (backup)
    _write_config("auto", merged)

def get_single_config() -> dict[str, Any]:
    return _read_config("single")

def save_single_config(cfg: dict) -> None:
    merged = _deep_merge(_DEFAULT_SINGLE, cfg)
    _write_config("single", merged)
