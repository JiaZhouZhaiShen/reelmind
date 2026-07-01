"""Speech-to-text service -- faster-whisper large-v3, float16.

Receives audio/video path, returns [{start, end, text}].
"""

from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any
from configs import whisper as whisper_cfg

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

logger = logging.getLogger(__name__)

_whisper_model = None
_whisper_model_name = ""
_whisper_load_failed = False


def _get_whisper():
    global _whisper_model, _whisper_model_name, _whisper_load_failed
    model_name = os.environ.get("WHISPER_MODEL") or whisper_cfg.model_size

    if _whisper_model is not None and _whisper_model_name == model_name:
        return _whisper_model

    _whisper_model = None
    _whisper_model_name = ""

    import torch
    from faster_whisper import WhisperModel

    compute_type = "float16" if torch.cuda.is_available() else "int8"
    device = "cuda" if torch.cuda.is_available() else "cpu"

    model_root = os.environ.get("MODEL_ROOT", "/data/reelmind/models")
    download_root = str(Path(model_root) / "faster-whisper")

    logger.info("Loading faster-whisper %s device=%s compute=%s", model_name, device, compute_type)
    try:
        _whisper_model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            download_root=download_root,
            cpu_threads=4,
            num_workers=2,
        )
        _whisper_model_name = model_name
    except Exception as e:
        logger.error("Whisper model load failed (cannot download): %s", e)
        _whisper_load_failed = True
        return None
    return _whisper_model


def transcribe(video_path: str | Path) -> list[dict[str, Any]]:
    model = _get_whisper()
    if model is None:
        logger.warning("Whisper not available, skipping transcription")
        return []

    # Pre-check: verify video has an accessible audio stream before calling Whisper
    try:
        import av
        container = av.open(str(video_path))
        audio_streams = [s for s in container.streams if s.type == "audio"]
        container.close()
        if not audio_streams:
            logger.info("No audio stream found in %s, skipping transcription", Path(video_path).name)
            return []
    except Exception as av_e:
        logger.warning("Cannot probe audio streams for %s: %s, proceeding anyway", Path(video_path).name, av_e)

    try:
        segments, info = model.transcribe(
            str(video_path),
            language=whisper_cfg.language or None,
            beam_size=whisper_cfg.beam_size,
            vad_filter=whisper_cfg.vad_filter,
            vad_parameters=dict(
                min_silence_duration_ms=whisper_cfg.min_silence_duration_ms,
                threshold=0.5,
                speech_pad_ms=100,
            ),
            without_timestamps=False,
            condition_on_previous_text=True,
        )

        results = []
        for seg in segments:
            results.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
                "language": info.language if info else "zh",
            })

        logger.info(
            "Transcribed %s: %d segments, language=%s, duration=%.1fs",
            Path(video_path).name, len(results),
            info.language if info else "?",
            info.duration if info else 0,
        )
        return results

    except Exception as exc:
        logger.exception("Whisper transcribe failed: %s", exc)
        return []

def _unload_whisper():
    global _whisper_model, _whisper_model_name, _whisper_load_failed
    if _whisper_model is None:
        return
    import gc
    logger.info('Unloading Whisper ...')
    _whisper_model = None
    _whisper_model_name = ''
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            alloc = torch.cuda.memory_allocated() / 1073741824
            logger.info('Whisper unloaded. CUDA: %.2f GB', alloc)
    except Exception:
        pass
