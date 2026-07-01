"""Pipeline orchestration configuration (scheduling, batching, etc.).

This is NOT a module config — it controls how the pipeline runner behaves.
"""
from __future__ import annotations
from configs.base import ModuleConfig


class PipelineConfig(ModuleConfig):
    """Configuration for the AI pipeline runner."""

    # Auto-run scheduler
    auto_run_enabled: bool = False
    # Start hour for auto-run window (0-23)
    auto_run_start_hour: int = 0
    # End hour for auto-run window (0-23)
    auto_run_end_hour: int = 23
    # GPU usage threshold % below which auto-run starts
    auto_run_gpu_threshold: int = 50
    # Check interval in minutes
    auto_run_check_interval: int = 1
    # Max videos per auto-run batch
    auto_run_max_videos: int = 10
    # Batch size for manual process-pending
    batch_size: int = 10
    # Max single file size in MB (files larger than this won't be processed)
    max_file_size_mb: int = 500
    # 循环批次: 手动批量处理时连续处理的批次数（-1 = 无限）
    batch_loop: int = 1

    # Active template name
    template: str = "quick_index"
