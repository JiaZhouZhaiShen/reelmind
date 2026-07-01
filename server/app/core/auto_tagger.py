"""Auto-tag videos from their metadata (resolution, codec, duration, fps, etc.)
and from EXIF data (camera, GPS, color science).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Resolution categories ──────────────────────────────────────────────────
RESOLUTION_TAGS: list[tuple[str, int]] = [
    ("8K", 7680),
    ("5K", 5120),
    ("4K", 3840),
    ("2K", 2560),
    ("1080p", 1920),
    ("720p", 1280),
    ("SD", 0),  # fallback
]

# ── Codec tags ─────────────────────────────────────────────────────────────
CODEC_TAGS: dict[str, str] = {
    "h264": "H.264",
    "hevc": "H.265/HEVC",
    "prores": "ProRes",
    "dnxhd": "DNxHD",
    "vp9": "VP9",
    "av1": "AV1",
    "mpeg4": "MPEG-4",
}

# ── Duration buckets (seconds) ─────────────────────────────────────────────
DURATION_BUCKETS: list[tuple[str, float, float]] = [
    ("short", 0, 30),
    ("clip", 30, 300),
    ("medium", 300, 1800),
    ("long", 1800, float("inf")),
]

# ── FPS categories ─────────────────────────────────────────────────────────
FPS_TAGS: list[tuple[str, float]] = [
    ("24fps", 24),
    ("25fps", 25),
    ("30fps", 30),
    ("50fps", 50),
    ("60fps", 60),
    ("high_fps", 120),
]

# ── Aspect ratio helpers ───────────────────────────────────────────────────
ASPECT_TAGS: dict[str, str] = {
    "landscape": "\u6a2a\u5c4f",
    "portrait": "\u7ad6\u5c4f",
    "square": "Square",
}

# ── Audio channel tags ─────────────────────────────────────────────────────
AUDIO_CHANNEL_TAGS: dict[int, str] = {
    1: "mono",
    2: "stereo",
    6: "surround_5.1",
    8: "surround_7.1",
}


def auto_generate_tags(meta: dict, exif: dict | None = None) -> list[dict]:
    """Return a list of {name, category, confidence} dicts from video metadata."""
    logger.debug("Generating auto-tags from meta keys: %s", list(meta.keys()))
    """Return a list of {name, category, confidence} dicts from video metadata.

    ``meta`` should contain keys like:
        width, height, duration, fps, codec,
        has_audio, audio_channels, mime_type, file_name

    ``exif`` (optional) may contain nested camera, gps, and color keys
    extracted by the indexer.
    """
    tags: list[dict] = []

    # ── Resolution ───────────────────────────────────────────────────────────
    width = meta.get("width") or 0
    height = meta.get("height") or 0
    max_dim = max(width, height)
    for label, threshold in RESOLUTION_TAGS:
        if max_dim >= threshold:
            tags.append({"name": label, "category": "resolution", "confidence": 1.0})
            break

    # ── Aspect ratio ─────────────────────────────────────────────────────────
    if width and height:
        ratio = width / height
        if 0.95 <= ratio <= 1.05:
            tags.append({"name": "Square", "category": "aspect_ratio", "confidence": 1.0})
        elif ratio > 1.05:
            tags.append({"name": "\u6a2a\u5c4f", "category": "aspect_ratio", "confidence": 1.0})
        else:
            tags.append({"name": "\u7ad6\u5c4f", "category": "aspect_ratio", "confidence": 1.0})

    # ── Codec ────────────────────────────────────────────────────────────────
    codec = (meta.get("codec") or "").lower()
    if codec in CODEC_TAGS:
        tags.append({"name": CODEC_TAGS[codec], "category": "codec", "confidence": 1.0})

    # ── Duration bucket ──────────────────────────────────────────────────────
    duration = meta.get("duration") or 0
    for label, lo, hi in DURATION_BUCKETS:
        if lo <= duration < hi:
            tags.append({"name": label, "category": "duration", "confidence": 1.0})
            break

    # ── FPS ──────────────────────────────────────────────────────────────────
    fps = meta.get("fps") or 0
    if fps > 70:
        tags.append({"name": "high_fps", "category": "fps", "confidence": 1.0})
    else:
        best = "24fps"
        best_diff = abs(fps - 24)
        for label, val in FPS_TAGS:
            diff = abs(fps - val)
            if diff < best_diff:
                best = label
                best_diff = diff
        tags.append({"name": best, "category": "fps", "confidence": 1.0})

    # ── Audio ────────────────────────────────────────────────────────────────
    has_audio = meta.get("has_audio", False)
    if has_audio:
        tags.append({"name": "has_audio", "category": "audio", "confidence": 1.0})
        channels = meta.get("audio_channels") or 2
        channel_tag = AUDIO_CHANNEL_TAGS.get(channels, f"{channels}ch")
        tags.append({"name": channel_tag, "category": "audio", "confidence": 1.0})
    else:
        tags.append({"name": "no_audio", "category": "audio", "confidence": 1.0})

    # ── File type ────────────────────────────────────────────────────────────
    file_name = meta.get("file_name") or ""
    ext = Path(file_name).suffix.lower().lstrip(".")
    if ext:
        tags.append({"name": ext, "category": "file_type", "confidence": 1.0})

    # ── Perceptual tags based on metadata ───────────────────────────────────
    if width and height:
        if width >= 3840 and height >= 2160:
            tags.append({"name": "ultra_hd", "category": "quality", "confidence": 0.9})
        elif width >= 1920:
            tags.append({"name": "hd", "category": "quality", "confidence": 0.9})
    if codec in ("prores", "dnxhd"):
        tags.append({"name": "professional", "category": "workflow", "confidence": 0.8})

# ── Camera make/model tags (from exif) ──────────────────────────────────
    if exif:
        camera = exif.get("camera") or {}
        cam_make = camera.get("make")
        cam_model = camera.get("model")
        if cam_make:
            tags.append({"name": f"camera:{cam_make}", "category": "camera", "confidence": 1.0})
        if cam_model:
            tags.append({"name": f"camera:{cam_model}", "category": "camera", "confidence": 1.0})
        if cam_make and cam_model:
            tags.append({"name": f"camera:{cam_make}_{cam_model}", "category": "camera", "confidence": 1.0})
        if camera.get("lens"):
            tags.append({"name": "has_lens_metadata", "category": "camera", "confidence": 0.9})

    # ── GPS / Location tags (from exif) ─────────────────────────────────────
        gps = exif.get("gps") or {}
        if gps.get("latitude") is not None and gps.get("longitude") is not None:
            tags.append({"name": "has_gps", "category": "location", "confidence": 1.0})
            # Rough hemisphere tags
            if float(gps["latitude"]) > 0:
                tags.append({"name": "northern_hemisphere", "category": "location", "confidence": 0.7})
            else:
                tags.append({"name": "southern_hemisphere", "category": "location", "confidence": 0.7})
            if float(gps["longitude"]) > 0:
                tags.append({"name": "eastern_hemisphere", "category": "location", "confidence": 0.7})
            else:
                tags.append({"name": "western_hemisphere", "category": "location", "confidence": 0.7})

    # ── HDR / Color science tags (from custom_metadata / tech) ──────────────
    tech = meta.get("custom_metadata") or {}
    if isinstance(tech, dict):
        col_prim = tech.get("color_primaries", "")
        col_trans = tech.get("color_transfer", "")
        if "bt2020" in str(col_prim).lower() or "smpte.st.2084" in str(col_trans).lower() or "pq" in str(col_trans).lower():
            tags.append({"name": "HDR", "category": "color", "confidence": 0.9})
        if "bt709" in str(col_prim).lower():
            tags.append({"name": "Rec.709", "category": "color", "confidence": 0.8})
        if "bt601" in str(col_prim).lower():
            tags.append({"name": "Rec.601", "category": "color", "confidence": 0.8})
        if "hlg" in str(col_trans).lower():
            tags.append({"name": "HLG", "category": "color", "confidence": 0.9})
        if "linear" in str(col_trans).lower():
            tags.append({"name": "log", "category": "color", "confidence": 0.7})
        if "srgb" in str(col_prim).lower():
            tags.append({"name": "sRGB", "category": "color", "confidence": 0.8})

        # Interlaced flag
        if tech.get("is_interlaced"):
            tags.append({"name": "interlaced", "category": "quality", "confidence": 1.0})

    # ── Audio codec tag ─────────────────────────────────────────────────────
    audio_codec = meta.get("audio_codec")
    if audio_codec:
        tags.append({"name": f"audio:{audio_codec}", "category": "audio", "confidence": 1.0})

    logger.debug("Auto-tags generated: %d tags — %s", len(tags), [t["name"] for t in tags])
    return tags
