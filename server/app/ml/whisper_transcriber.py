"""ReelMind 语音转文字 —— faster-whisper (CTranslate2 后端)

比 openai-whisper:
  - 快 3~4 倍（INT8 量化）
  - 显存省 ~60%
  - 内置 VAD 自动切分静音段
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from ..config import settings

logger = logging.getLogger(__name__)

# ── 单例 ────────────────────────────────────────────────────────────────────
_whisper_model = None
_whisper_model_name: str = ""


def _load_whisper(model_name: str | None = None) -> Any:
    """全局单例 WhisperModel（惰性加载，跨任务复用）。"""
    global _whisper_model, _whisper_model_name

    if model_name is None:
        model_name = settings.WHISPER_MODEL or "tiny"

    if _whisper_model is not None and _whisper_model_name == model_name:
        return _whisper_model

    # 释放旧模型（如有）
    _whisper_model = None

    import torch

    compute_type = "float16" if torch.cuda.is_available() else "int8"
    device = "cuda" if torch.cuda.is_available() else "cpu"

    from faster_whisper import WhisperModel  # noqa: PLC0415

    logger.info(
        "Loading faster-whisper model=%s device=%s compute=%s",
        model_name, device, compute_type,
    )
    _whisper_model = WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
        download_root=str(settings.MODEL_ROOT / "faster-whisper"),
    )
    _whisper_model_name = model_name
    return _whisper_model


def transcribe(
    video_path: str | Path,
    model_name: str | None = None,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """将视频语音转为文字段。

    Returns:
        按时间排序的片段列表，每段含 start / end / text / language。
        返回空列表表示未启用或失败。
    """
    if not settings.ENABLE_WHISPER:
        return []

    model = _load_whisper(model_name)
    if model is None:
        logger.error("faster-whisper model failed to load")
        return []

    try:
        segments, info = model.transcribe(
            str(video_path),
            language=language,
            beam_size=5,
            vad_filter=True,                       # 自动跳过静音段
            vad_parameters=dict(
                min_silence_duration_ms=500,
                threshold=0.5,
            ),
            without_timestamps=False,
            condition_on_previous_text=True,
        )

        results: list[dict[str, Any]] = []
        for seg in segments:
            results.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
                "language": info.language if info else "en",
            })

        logger.info(
            "Transcribed %s: %d segments, language=%s, duration=%.1fs",
            Path(video_path).name, len(results),
            info.language if info else "?",
            info.duration if info else 0,
        )
        return results

    except Exception as exc:
        logger.exception("faster-whisper transcribe failed: %s", exc)
        return []


def transcribe_fallback_whisper_cpp(
    video_path: str | Path,
) -> list[dict[str, Any]]:
    """备用方案：whisper.cpp（已弃用，仅作兼容保留）。"""
    import subprocess
    import tempfile

    segments: list[dict[str, Any]] = []
    audio_path = Path(tempfile.mktemp(suffix=".wav"))
    try:
        subprocess.run(
            [
                settings.FFMPEG_PATH, "-y", "-i", str(video_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000",
                "-ac", "1", str(audio_path),
            ],
            capture_output=True, timeout=300, check=True,
        )

        result = subprocess.run(
            ["whisper-cpp", "-f", str(audio_path), "-otxt", "-oj"],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            import json
            json_path = audio_path.with_suffix(".json")
            if json_path.exists():
                data = json.loads(json_path.read_text())
                for seg in data.get("segments", []):
                    segments.append({
                        "start": seg["start"],
                        "end": seg["end"],
                        "text": seg["text"].strip(),
                        "language": "en",
                    })
    finally:
        audio_path.unlink(missing_ok=True)
        for suff in (".json", ".txt", ".srt", ".vtt"):
            p = audio_path.with_suffix(suff)
            p.unlink(missing_ok=True)
    return segments
