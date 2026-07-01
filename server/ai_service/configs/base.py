"""Base class for per-module AI configuration."""
from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("configs")


def _config_dir() -> Path:
    """Return the directory where config JSON files are stored.

    Uses DATA_ROOT/configs/ so configs persist across container restarts
    and are accessible from the host volume mount.
    """
    data_root = Path(os.environ.get("DATA_ROOT", "/data/reelmind/data"))
    cfg_dir = data_root / "configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


class ModuleConfig:
    """Base class for an individual AI module's configuration.

    Subclasses define default values as class attributes.
    Each module gets its own JSON file for persistence.
    """

    # Every module has an enabled flag
    enabled: bool = True

    # Module name (used as JSON filename)
    _module_name: str = ""

    def __init__(self, **kwargs):
        if not self._module_name:
            self._module_name = self.__class__.__name__.lower().replace("config", "")
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    @property
    def _file_path(self) -> Path:
        return _config_dir() / f"{self._module_name}.json"

    def to_dict(self) -> dict[str, Any]:
        """Serialize this config to a dict (excluding private attrs)."""
        result = {}
        for k, v in self.__class__.__dict__.items():
            if not k.startswith("_") and not callable(v):
                result[k] = getattr(self, k, v)
        for k, v in self.__dict__.items():
            if not k.startswith("_"):
                result[k] = v
        return result

    def from_dict(self, data: dict[str, Any]) -> "ModuleConfig":
        """Restore from a dict (only known keys)."""
        for k, v in data.items():
            if hasattr(self, k):
                setattr(self, k, v)
        return self

    def save(self):
        """Persist to JSON file."""
        fpath = self._file_path
        try:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info("Saved config '%s' to %s", self._module_name, fpath)
        except Exception as e:
            logger.warning("Failed to save config '%s': %s", self._module_name, e)

    def load(self):
        """Load from JSON file (silently fall back to defaults)."""
        fpath = self._file_path
        if not fpath.exists():
            logger.debug("No saved config for '%s', using defaults", self._module_name)
            return
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.from_dict(data)
            logger.info("Loaded config '%s' from %s", self._module_name, fpath)
        except Exception as e:
            logger.warning("Failed to load config '%s': %s", self._module_name, e)

    def __repr__(self) -> str:
        items = ", ".join(f"{k}={v}" for k, v in self.to_dict().items())
        return f"{self.__class__.__name__}({items})"