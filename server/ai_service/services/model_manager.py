"""CUDA memory manager -- serial load/unload large models, peak under 4GB."""

from __future__ import annotations
import gc
import logging
import os
from typing import Any, Callable

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

logger = logging.getLogger(__name__)


class ModelManager:
    _instance = None
    _current_model = None
    _loaders = {}
    _loaded_model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, name: str, loader):
        cls._loaders[name] = loader

    @classmethod
    def load(cls, name: str):
        if cls._current_model == name and cls._loaded_model is not None:
            return cls._loaded_model
        cls.unload()
        loader = cls._loaders.get(name)
        if loader is None:
            raise ValueError("Unknown model: " + name)
        log = logging.getLogger(__name__)
        log.info("Loading model %s ...", name)
        model = loader()
        cls._loaded_model = model
        cls._current_model = name
        import torch
        if torch.cuda.is_available():
            alloc = torch.cuda.memory_allocated() / 1073741824
            log.info("Model %s loaded. CUDA memory: %.2f GB", name, alloc)
        return model

    @classmethod
    def unload(cls):
        if cls._current_model is None:
            return
        log = logging.getLogger(__name__)
        log.info("Unloading model %s ...", cls._current_model)
        cls._loaded_model = None
        cls._current_model = None
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            alloc = torch.cuda.memory_allocated() / 1073741824
            log.info("CUDA memory after unload: %.2f GB", alloc)

    @classmethod
    def current(cls):
        return cls._current_model

    @classmethod
    def get_loaded(cls):
        return cls._loaded_model
