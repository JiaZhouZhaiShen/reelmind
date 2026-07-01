"""PaddleOCR text recognition configuration."""
from __future__ import annotations
from configs.base import ModuleConfig


class OcrConfig(ModuleConfig):
    """Configuration for PaddleOCR text recognition."""

    enabled: bool = True
    # OCR language (ch, en, chinese_cht, japan, korean)
    lang: str = "ch"
    # Minimum confidence threshold for text detection (code filters at 0.7)
    confidence_threshold: float = 0.7
    # Use GPU for inference
    use_gpu: bool = True
    # Max text length to recognize
    max_text_length: int = 25
    # DB detector threshold
    det_db_threshold: float = 0.45
    # Recognition batch size
    rec_batch_num: int = 6
