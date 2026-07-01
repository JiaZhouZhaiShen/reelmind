"""Speaker diarization service -- pyannote.audio speaker-diarization-3.1.

Pipeline:
  1. ffmpeg extract 16kHz mono audio
  2. Run diarization to get speaker segments
  3. Merge with Whisper subtitles by time overlap
"""

from __future__ import annotations
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from configs import diarization as diarization_cfg

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

logger = logging.getLogger(__name__)

_diarization_pipeline = None


def _load_diarization():
    global _diarization_pipeline
    if _diarization_pipeline is not None:
        return _diarization_pipeline

    hf_token = os.environ.get("HUGGINGFACE_TOKEN", "")
    if not hf_token:
        logger.warning("HUGGINGFACE_TOKEN not set, diarization will be skipped")
        return None

    from pyannote.audio import Pipeline

    logger.info("Loading diarization pipeline %s ...", diarization_cfg.pipeline_name)
    _diarization_pipeline = Pipeline.from_pretrained(
        diarization_cfg.pipeline_name,
        use_auth_token=hf_token,
    )

    import torch
    if torch.cuda.is_available():
        _diarization_pipeline.to(torch.device(diarization_cfg.device))
        alloc = torch.cuda.memory_allocated() / 1073741824
        logger.info("Diarization pipeline loaded. CUDA: %.2f GB", alloc)

    return _diarization_pipeline


def extract_audio(video_path: str | Path) -> str | None:
    """Extract 16kHz mono WAV from video. Returns path to temp file."""
    import tempfile
    fd, audio_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                audio_path,
            ],
            capture_output=True, timeout=600, check=True,
        )
        return audio_path
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg audio extraction timed out for %s", video_path)
        os.unlink(audio_path)
        return None
    except subprocess.CalledProcessError as e:
        logger.error("ffmpeg audio extraction failed: %s", e.stderr.decode()[:500])
        os.unlink(audio_path)
        return None
    except Exception as e:
        logger.error("Audio extraction error: %s", e)
        try:
            os.unlink(audio_path)
        except Exception:
            pass
        return None


def run_diarization(audio_path: str) -> list[dict[str, Any]]:
    """Run speaker diarization on audio file.

    Returns:
        [{start, end, speaker}, ...]
    """
    pipeline = _load_diarization()
    if pipeline is None:
        return []

    try:
        kwargs = {}
        if diarization_cfg.num_speakers is not None:
            kwargs["num_speakers"] = diarization_cfg.num_speakers
        if diarization_cfg.min_speakers is not None:
            kwargs["min_speakers"] = diarization_cfg.min_speakers
        if diarization_cfg.max_speakers is not None:
            kwargs["max_speakers"] = diarization_cfg.max_speakers
        diarization = pipeline(audio_path, **kwargs)
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
                "speaker": str(speaker),
            })
        return segments
    except Exception as e:
        logger.exception("Diarization failed: %s", e)
        return []


def merge_speakers_with_subtitles(
    subtitles: list[dict],
    speaker_segments: list[dict],
) -> list[dict]:
    """Merge speaker labels into subtitle segments by time overlap.

    Each subtitle gets assigned the speaker with max overlap.
    """
    if not speaker_segments:
        return subtitles

    merged = []
    for sub in subtitles:
        s_start = sub["start"]
        s_end = sub["end"]
        s_dur = s_end - s_start
        best_speaker = None
        best_overlap = 0.0

        for sp in speaker_segments:
            overlap_start = max(s_start, sp["start"])
            overlap_end = min(s_end, sp["end"])
            overlap = max(0.0, overlap_end - overlap_start)
            if overlap > best_overlap and overlap > 0.1:
                best_overlap = overlap
                best_speaker = sp["speaker"]

        sub["speaker"] = best_speaker
        merged.append(sub)

    return merged


def process(video_path: str | Path, subtitles: list[dict]) -> list[dict]:
    """Full pipeline: extract audio -> diarize -> merge with subtitles.

    Returns:
        Subtitles with speaker field filled.
    """
    audio_path = extract_audio(video_path)
    if audio_path is None:
        return subtitles

    try:
        speaker_segments = run_diarization(audio_path)
        if not speaker_segments:
            logger.info("No speaker segments found for %s", Path(video_path).name)
            return subtitles

        merged = merge_speakers_with_subtitles(subtitles, speaker_segments)
        speaker_count = len(set(s["speaker"] for s in merged if s.get("speaker")))
        logger.info(
            "Diarization done: %s -> %d speakers, %d subtitle segments labeled",
            Path(video_path).name, speaker_count, len(merged),
        )
        return merged
    finally:
        try:
            os.unlink(audio_path)
        except Exception:
            pass

def _unload_diarization():
    global _diarization_pipeline
    if _diarization_pipeline is None:
        return
    import gc
    logger.info('Unloading diarization ...')
    _diarization_pipeline = None
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            alloc = torch.cuda.memory_allocated() / 1073741824
            logger.info('Diarization unloaded. CUDA: %.2f GB', alloc)
    except Exception:
        pass
