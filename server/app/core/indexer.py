from __future__ import annotations
import asyncio
import datetime as dt_mod
import json
import logging
import re
import subprocess
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text as _sql_text
import time
import uuid
from ..config import settings
from ..core.job_helpers import ENGINES, ENGINE_DEPENDS
from ..models.ai_engine_job import AIEngineJob
from ..core import settings_cache as _scache

logger = logging.getLogger(__name__)

# =========================================================================
# Metadata field registry (unchanged from original)
# =========================================================================

METADATA_FIELD_DEFINITIONS: dict[str, dict[str, str]] = OrderedDict({
    # -- Resolution --
    "width": {"key": "width", "label": "Width (px)", "description": "Video width in pixels", "category": "basic", "group": "resolution"},
    "height": {"key": "height", "label": "Height (px)", "description": "Video height in pixels", "category": "basic", "group": "resolution"},
    "fps": {"key": "fps", "label": "FPS", "description": "Frames per second", "category": "basic", "group": "resolution"},
    # -- Codec --
    "codec": {"key": "codec", "label": "Video Codec", "description": "Video codec name (e.g. h264)", "category": "basic", "group": "codec"},
    "codec_long_name": {"key": "codec_long_name", "label": "Codec Long Name", "description": "Full codec name", "category": "custom_metadata", "group": "codec"},
    "pixel_format": {"key": "pixel_format", "label": "Pixel Format", "description": "Pixel format (e.g. yuv420p)", "category": "custom_metadata", "group": "codec"},
    "color_space": {"key": "color_space", "label": "Color Space", "description": "Color space (e.g. bt709)", "category": "custom_metadata", "group": "codec"},
    "color_primaries": {"key": "color_primaries", "label": "Color Primaries", "description": "Color primaries", "category": "custom_metadata", "group": "codec"},
    "color_transfer": {"key": "color_transfer", "label": "Color Transfer", "description": "Color transfer function", "category": "custom_metadata", "group": "codec"},
    "field_order": {"key": "field_order", "label": "Field Order", "description": "Video field order (progressive/interlaced)", "category": "custom_metadata", "group": "codec"},
    "is_interlaced": {"key": "is_interlaced", "label": "Interlaced", "description": "Whether the video is interlaced", "category": "custom_metadata", "group": "codec"},
    "format_name": {"key": "format_name", "label": "Container Format", "description": "Media container format (e.g. mp4, mov)", "category": "custom_metadata", "group": "codec"},
    # -- Audio --
    "audio_codec": {"key": "audio_codec", "label": "Audio Codec", "description": "Audio codec name", "category": "basic", "group": "audio"},
    "audio_channels": {"key": "audio_channels", "label": "Audio Channels", "description": "Number of audio channels", "category": "basic", "group": "audio"},
    "has_audio": {"key": "has_audio", "label": "Has Audio", "description": "Whether the file has an audio track", "category": "basic", "group": "audio"},
    "audio_sample_rate": {"key": "audio_sample_rate", "label": "Audio Sample Rate (Hz)", "description": "Audio sample rate in Hz", "category": "custom_metadata", "group": "audio"},
    "audio_bitrate": {"key": "audio_bitrate", "label": "Audio Bitrate (bps)", "description": "Audio bitrate in bps", "category": "custom_metadata", "group": "audio"},
    # -- Camera --
    "camera_make": {"key": "camera_make", "label": "Camera Make", "description": "Camera manufacturer", "category": "exif", "group": "camera"},
    "camera_model": {"key": "camera_model", "label": "Camera Model", "description": "Camera model name", "category": "exif", "group": "camera"},
    "camera_software": {"key": "camera_software", "label": "Camera Software", "description": "Camera software/encoder", "category": "exif", "group": "camera"},
    "lens_model": {"key": "lens_model", "label": "Lens Model", "description": "Lens model used", "category": "exif", "group": "camera"},
    # -- GPS --
    "gps_latitude": {"key": "gps_latitude", "label": "GPS Latitude", "description": "GPS latitude coordinate", "category": "exif", "group": "gps"},
    "gps_longitude": {"key": "gps_longitude", "label": "GPS Longitude", "description": "GPS longitude coordinate", "category": "exif", "group": "gps"},
    "gps_altitude": {"key": "gps_altitude", "label": "GPS Altitude (m)", "description": "GPS altitude in meters", "category": "exif", "group": "gps"},
    # -- Technical --
    "video_bitrate": {"key": "video_bitrate", "label": "Video Bitrate (bps)", "description": "Total video bitrate", "category": "basic", "group": "technical"},
    "total_bitrate": {"key": "total_bitrate", "label": "Total Bitrate (bps)", "description": "Overall bitrate", "category": "custom_metadata", "group": "technical"},
    # -- File --
    "duration": {"key": "duration", "label": "Duration (s)", "description": "Video duration in seconds", "category": "basic", "group": "file"},
    "media_date": {"key": "media_date", "label": "Recording Date", "description": "Original recording date/time", "category": "basic", "group": "file"},
})

ALL_METADATA_KEYS = list(METADATA_FIELD_DEFINITIONS.keys())

METADATA_GROUP_ORDER = ["resolution", "codec", "audio", "camera", "gps", "technical", "file"]


def get_metadata_field_definitions() -> list[dict[str, str]]:
    """Return all available metadata field definitions for UI configuration."""
    return [dict(v) for v in METADATA_FIELD_DEFINITIONS.values()]


def _filter_metadata(meta: dict[str, Any], included: set[str]) -> dict[str, Any]:
    """Filter extracted metadata to only included fields."""
    if not included:
        return meta
    basic, exif, cm = meta.get("basic", {}), meta.get("exif", {}), meta.get("custom_metadata", {})
    filtered_basic = {}
    filtered_exif = {}
    filtered_cm = {}
    for field_key in METADATA_FIELD_DEFINITIONS:
        if field_key not in included:
            continue
        defn = METADATA_FIELD_DEFINITIONS[field_key]
        cat = defn["category"]
        if cat == "basic" and field_key in basic:
            filtered_basic[field_key] = basic[field_key]
        elif cat == "exif":
            if field_key.startswith("camera_"):
                sub_key = field_key.replace("camera_", "")
                if "camera" in exif and sub_key in exif["camera"]:
                    filtered_exif.setdefault("camera", {})[sub_key] = exif["camera"][sub_key]
            elif field_key.startswith("gps_"):
                sub_key = field_key.replace("gps_", "")
                if "gps" in exif and sub_key in exif["gps"]:
                    filtered_exif.setdefault("gps", {})[sub_key] = exif["gps"][sub_key]
        elif cat == "custom_metadata" and field_key in cm:
            filtered_cm[field_key] = cm[field_key]
    result = {}
    if filtered_basic:
        result["basic"] = filtered_basic
    if filtered_exif:
        result["exif"] = filtered_exif
    if filtered_cm:
        result["custom_metadata"] = filtered_cm
    return result


# =========================================================================
# Async ffprobe (performance-optimized)
# =========================================================================

class ProbeStats:
    """Track ffprobe statistics across a scan batch."""
    def __init__(self):
        self.total = 0
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.elapsed_seconds = 0.0

    @property
    def summary(self) -> dict:
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


_global_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Get or create the global ffprobe concurrency semaphore."""
    global _global_semaphore
    _ffprobe_concurrency = _scache.get_int("ffprobe_concurrency", settings.FFPROBE_CONCURRENCY)
    if _global_semaphore is None or _global_semaphore._value != _ffprobe_concurrency:
        _global_semaphore = asyncio.Semaphore(_ffprobe_concurrency)
    return _global_semaphore


_thumbnail_semaphore_global: asyncio.Semaphore | None = None


def _get_thumbnail_semaphore() -> asyncio.Semaphore:
    """Get or create the global thumbnail concurrency semaphore."""
    global _thumbnail_semaphore_global
    concurrency = _scache.get_int("thumbnail_concurrency", 4)
    if _thumbnail_semaphore_global is None or _thumbnail_semaphore_global._value != concurrency:
        _thumbnail_semaphore_global = asyncio.Semaphore(concurrency)
    return _thumbnail_semaphore_global


async def probe_video_async(path: str | Path) -> dict[str, Any]:
    """Async ffprobe with concurrency semaphore and safety flags.
        Core performance optimization:
    - Uses asyncio.create_subprocess_exec instead of blocking subprocess.run
    - Respects FFPROBE_CONCURRENCY via asyncio.Semaphore
    - Adds -analyzeduration and -probesize to prevent hang on corrupted files
    - Has timeout to prevent indefinite blocking
    """
    sem = _get_semaphore()
    async with sem:
        logger.info("Probing video (async): %s", path)
        cmd = [
            settings.FFPROBE_PATH,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            "-analyzeduration", settings.FFPROBE_ANALYZE_DURATION,
            "-probesize", settings.FFPROBE_PROBE_SIZE,
            str(path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _ffprobe_timeout = _scache.get_int("ffprobe_timeout", settings.FFPROBE_TIMEOUT)
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=_ffprobe_timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                logger.error("ffprobe timed out (%ds) for %s", _ffprobe_timeout, path)
                raise RuntimeError(f"ffprobe timed out after {_ffprobe_timeout}s")

            if proc.returncode != 0:
                stderr_text = stderr.decode("utf-8", errors="replace")[:500]
                logger.error("ffprobe failed for %s (rc=%d): %s", path, proc.returncode, stderr_text)
                raise RuntimeError(f"ffprobe failed: {stderr_text}")

            data = json.loads(stdout.decode("utf-8"))
            logger.debug("ffprobe OK for %s 鈥?format=%s, streams=%d",
                        path, data.get("format", {}).get("format_name", "?"),
                        len(data.get("streams", [])))
            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.error("ffprobe error for %s: %s", path, e)
            raise RuntimeError(f"ffprobe error: {e}")


# =========================================================================
# Sync wrapper (backward compatible for existing callers)
# =========================================================================

def probe_video(path: str | Path) -> dict[str, Any]:
    """Synchronous ffprobe (backward compatible).
        Also adds safety flags -analyzeduration/-probesize.
    """
    logger.info("Probing video (sync): %s", path)
    cmd = [
        settings.FFPROBE_PATH,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-analyzeduration", settings.FFPROBE_ANALYZE_DURATION,
        "-probesize", settings.FFPROBE_PROBE_SIZE,
        str(path),
    ]
    try:
        _ffprobe_timeout = _scache.get_int("ffprobe_timeout", settings.FFPROBE_TIMEOUT)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_ffprobe_timeout)
    except subprocess.TimeoutExpired:
        logger.error("ffprobe sync timed out (%ds) for %s", _ffprobe_timeout, path)
        raise RuntimeError(f"ffprobe timed out after {_ffprobe_timeout}s")

    if result.returncode != 0:
        logger.error("ffprobe failed for %s (rc=%d): %s", path, result.returncode, result.stderr[:500])
        raise RuntimeError(f"ffprobe failed: {result.stderr[:500]}")
    data = json.loads(result.stdout)
    logger.debug("ffprobe OK for %s 鈥?format=%s, streams=%d",
                 path, data.get("format", {}).get("format_name", "?"),
                 len(data.get("streams", [])))
    return data


# =========================================================================
# ISO 6709 parser (unchanged)
# =========================================================================

def parse_iso6709(iso6709: str) -> dict[str, float | None] | None:
    """Parse ISO 6709 coordinate string into lat/lon/alt."""
    logger.debug("Parsing ISO6709 coordinate: %s", iso6709)
    m = re.match(r'^([+-]\d+\.?\d*)([+-]\d+\.?\d*)([+-]\d+\.?\d*)?/?$', iso6709.strip())
    if not m:
        logger.warning("Failed to parse ISO6709 coordinate: %s", iso6709)
        return None
    lat = float(m.group(1))
    lon = float(m.group(2))
    alt = float(m.group(3)) if m.group(3) else None
    logger.debug("Parsed ISO6709 鈫?lat=%.4f, lon=%.4f, alt=%s", lat, lon, alt)
    return {"latitude": lat, "longitude": lon, "altitude": alt}


# =========================================================================
# Metadata extraction (unchanged logic, reused by both sync and async)
# =========================================================================

def _parse_fps(stream: dict) -> float | None:
    r_frame_rate = stream.get("r_frame_rate", "0/0")
    try:
        num, den = r_frame_rate.split("/")
        if int(den) > 0:
            return round(float(num) / float(den), 3)
    except (ValueError, ZeroDivisionError):
        pass
    return None


def _parse_media_date(media_date_str: str | None) -> dt_mod.datetime | None:
    """Parse a media date string to a datetime object."""
    if not media_date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d", "%Y:%m:%d %H:%M:%S"):
        try:
            return dt_mod.datetime.strptime(media_date_str.strip().replace("Z", "+0000"), fmt)
        except ValueError:
            continue
    return None


def _raw_extract_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """Core metadata extraction from raw ffprobe output. No I/O."""
    fmt = data.get("format", {})
    fmt_tags = fmt.get("tags", {})
    streams = data.get("streams", [])

    video_stream = None
    audio_stream = None
    for s in streams:
        ctype = s.get("codec_type")
        if ctype == "video" and video_stream is None:
            video_stream = s
        elif ctype == "audio" and audio_stream is None:
            audio_stream = s

    v_tags = (video_stream or {}).get("tags", {})
    v_codec_name = (video_stream or {}).get("codec_name")
    v_codec_long = (video_stream or {}).get("codec_long_name")
    field_order = (video_stream or {}).get("field_order", "")
    is_interlaced = field_order in ("tt", "bb", "tb", "bt", "interlaced")

    a_codec_name = (audio_stream or {}).get("codec_name")
    a_sample_rate = int((audio_stream or {}).get("sample_rate", 0)) if audio_stream else None
    a_bit_rate_val = int((audio_stream or {}).get("bit_rate", 0)) if audio_stream else None
    fmt_bit_rate = int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else None
    fmt_duration = float(fmt.get("duration", 0))

    # Camera info from format tags
    camera_make = (fmt_tags.get("com.apple.quicktime.make") or fmt_tags.get("make") or fmt_tags.get("Make") or v_tags.get("make"))
    camera_model = (fmt_tags.get("com.apple.quicktime.model") or fmt_tags.get("model") or fmt_tags.get("Model") or v_tags.get("model"))
    camera_software = (fmt_tags.get("com.apple.quicktime.software") or fmt_tags.get("software") or fmt_tags.get("encoder"))
    lens_model = (v_tags.get("lens") or v_tags.get("lens_model") or fmt_tags.get("com.apple.quicktime.lens.model"))

    # Creation date
    media_date_str = (fmt_tags.get("com.apple.quicktime.creationdate") or fmt_tags.get("creation_time") or v_tags.get("creation_time"))

    # GPS
    location_iso = fmt_tags.get("com.apple.quicktime.location.ISO6709")
    gps_coords = None
    if location_iso:
        gps_coords = parse_iso6709(location_iso)
    if not gps_coords:
        try:
            lat_ref = fmt_tags.get("com.apple.quicktime.GPSLatitudeRef") or fmt_tags.get("GPSLatitudeRef")
            lat_val = fmt_tags.get("com.apple.quicktime.GPSLatitude") or fmt_tags.get("GPSLatitude")
            lon_ref = fmt_tags.get("com.apple.quicktime.GPSLongitudeRef") or fmt_tags.get("GPSLongitudeRef")
            lon_val = fmt_tags.get("com.apple.quicktime.GPSLongitude") or fmt_tags.get("GPSLongitude")
            if lat_val and lon_val:
                lat = float(lat_val)
                lon = float(lon_val)
                if lat_ref and lat_ref.upper() == "S": lat = -lat
                if lon_ref and lon_ref.upper() == "W": lon = -lon
                gps_coords = {"latitude": lat, "longitude": lon, "altitude": None}
        except (ValueError, TypeError):
            pass

    # --- Rotation-aware width/height correction ---
    _rotation = 0
    rotate_tag = v_tags.get("rotate")
    if rotate_tag is not None:
        _rotation = int(rotate_tag) % 360
    if _rotation == 0:
        side_data_list = (video_stream or {}).get("side_data_list", [])
        for sd in side_data_list:
            if sd.get("side_data_type") == "Display Matrix":
                r = sd.get("rotation")
                if r is not None:
                    _rotation = int(r) % 360
                    break

    raw_w = int(video_stream.get("width", 0)) if video_stream else None
    raw_h = int(video_stream.get("height", 0)) if video_stream else None
    if _rotation in (90, 270) and raw_w is not None and raw_h is not None:
        display_w, display_h = raw_h, raw_w
    else:
        display_w, display_h = raw_w, raw_h

    # 1. Basic fields
    basic: dict[str, Any] = {
        "width": display_w,
        "height": display_h,
        "duration": fmt_duration,
        "fps": _parse_fps(video_stream) if video_stream else None,
        "codec": v_codec_name,
        "video_bitrate": fmt_bit_rate,
        "audio_codec": a_codec_name,
        "audio_channels": int(audio_stream.get("channels", 0)) if audio_stream else None,
        "has_audio": audio_stream is not None,
        "media_date": _parse_media_date(media_date_str),
    }

    # 2. EXIF / camera / GPS
    exif_data: dict[str, Any] = {}
    cam_block: dict[str, str] = {}
    if camera_make: cam_block["make"] = camera_make
    if camera_model: cam_block["model"] = camera_model
    if camera_software: cam_block["software"] = camera_software
    if lens_model: cam_block["lens"] = lens_model
    if cam_block: exif_data["camera"] = cam_block
    if gps_coords: exif_data["gps"] = gps_coords

    # 3. Technical details
    tech_data: dict[str, Any] = {
        "codec_long_name": v_codec_long,
        "pixel_format": (video_stream or {}).get("pix_fmt"),
        "color_space": (video_stream or {}).get("color_space"),
        "color_primaries": (video_stream or {}).get("color_primaries"),
        "color_transfer": (video_stream or {}).get("color_transfer"),
        "field_order": field_order,
        "is_interlaced": is_interlaced,
        "audio_sample_rate": a_sample_rate,
        "audio_bitrate": a_bit_rate_val,
        "format_name": fmt.get("format_name"),
        "total_bitrate": fmt_bit_rate,
    }

    return {"basic": basic, "exif": exif_data, "custom_metadata": tech_data}


def extract_metadata(path: str | Path, included_fields: list[str] | None = None) -> dict[str, Any]:
    """Synchronous metadata extraction (backward compatible)."""
    data = probe_video(path)
    return _finalize_metadata(data, included_fields)


async def extract_metadata_async(path: str | Path, included_fields: list[str] | None = None) -> dict[str, Any]:
    """Async metadata extraction with semaphore-controlled ffprobe."""
    data = await probe_video_async(path)
    return _finalize_metadata(data, included_fields)


def _finalize_metadata(data: dict[str, Any], included_fields: list[str] | None = None) -> dict[str, Any]:
    """Convert raw ffprobe output to structured metadata, optionally filtered."""
    result = _raw_extract_metadata(data)
    if included_fields is not None:
        return _filter_metadata(result, set(included_fields))
    return result


# =========================================================================
# Batch async indexer 鈥?runs parallel ffprobe with configurable concurrency
# =========================================================================

async def batch_index_metadata(
    items: list[dict[str, Any]],
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    """Process a batch of video files through async ffprobe concurrently.
        Args:
        items: List of dicts with at least {"asset_id": str, "video_path": str}
               Optional: {"included_fields": list[str]}
        progress_callback: Called as callback(completed, total) after each file
        cancel_check: Called before each file; return True to abort
        Returns:
        List of result dicts, each with:
            asset_id, status ("ok"/"error"), metadata (on success), error (on failure)
    """
    stats = ProbeStats()
    stats.total = len(items)
    start_time = dt_mod.datetime.now(dt_mod.timezone.utc)

    sem = _get_semaphore()
    logger.info("Batch metadata index: %d items, concurrency=%d", len(items), sem._value)

    async def _process_one(item: dict[str, Any]) -> dict[str, Any]:
        nonlocal stats
        if cancel_check and cancel_check():
            return {"asset_id": item["asset_id"], "status": "cancelled"}

        aid = item["asset_id"]
        vpath = item["video_path"]
        included = item.get("included_fields")

        try:
            meta = await extract_metadata_async(vpath, included)
            stats.success += 1
            return {"asset_id": aid, "status": "ok", "metadata": meta}
        except Exception as e:
            stats.failed += 1
            logger.warning("Metadata extraction failed for asset %s (%s): %s", aid, vpath, e)
            return {"asset_id": aid, "status": "error", "error": str(e)[:500]}
        finally:
            if progress_callback:
                progress_callback(stats.success + stats.failed, stats.total)

    # Launch all tasks concurrently 鈥?Semaphore limits actual ffprobe processes
    tasks = [_process_one(item) for item in items]
    results = await asyncio.gather(*tasks)

    stats.elapsed_seconds = (dt_mod.datetime.now(dt_mod.timezone.utc) - start_time).total_seconds()
    logger.info("Batch metadata index done: %s (%.1f files/sec)",
                stats.summary,
                stats.success / stats.elapsed_seconds if stats.elapsed_seconds > 0 else 0)
    return results

# ============================================================================
# IndexingService 鈥?class-based, Celery-free, Semaphore-controlled scanner
# ============================================================================
"""
High-level scanning orchestrator.

Separates file discovery (scanning) from metadata probing (ffprobe).
Uses asyncio.Semaphore to limit concurrency.
Publishes progress via Redis pubsub 鈫?SSE for real-time frontend updates.
"""

from ..database import async_session_factory
from ..models import Asset, Library, LibraryPath, Job
from .scanner import scandir_walk, scan_directory, is_video_file

# Re-export for convenience
__all__ = ["IndexingService", "batch_index_metadata", "probe_video", "probe_video_async",
            "extract_metadata", "extract_metadata_async", "ProbeStats",
            "METADATA_FIELD_DEFINITIONS", "ALL_METADATA_KEYS"]


class IndexingService:
    """
    Orchestrates a full library scan:

    1. Step A (discovery): walks root_path, collects all video file paths.
        Does NOT call ffprobe 鈥?just filesystem iteration.
    2. Step B (probing): feeds discovered files into a Semaphore-guarded
        async worker pool that calls probe_video_async().
    3. Batch writer: every METADATA_BATCH_SIZE results, issues one bulk
        UPSERT so the DB isn't hammered with single-row commits.
    4. Progress: publishes {total, done, failed, stage} to Redis pubsub,
        which feeds SSE endpoints for real-time frontend progress bars.
    """

    def __init__(self):
        self._logger = logging.getLogger("reelmind.indexer.service")
        self._active_scans: dict[str, dict] = {}  # scan_id -> scan_info
        self._cancel_events: dict[str, asyncio.Event] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_scan(
        self,
        library_id: str,
        root_path: str,
        custom_extensions: list[str] | None = None,
        excluded_extensions: list[str] | None = None,
        included_fields: list[str] | None = None,
        job_id: str | None = None,
    ) -> str:
        """
        Begin a full scan of *root_path* for the given library.

        Returns a scan_id (UUID string) that can be used to poll status
        or cancel the scan.
        """
        scan_id = str(uuid.uuid4())
        self._cancel_events[scan_id] = asyncio.Event()

        # Fire-and-forget the scan in the background
        asyncio.create_task(
            self._run_scan(
                scan_id=scan_id,
                library_id=library_id,
                root_path=root_path,
                custom_extensions=custom_extensions,
                excluded_extensions=excluded_extensions,
                included_fields=included_fields,
                job_id=job_id,
            )
        )
        self._logger.info("Scan started: scan_id=%s library=%s path=%s",
                         scan_id, library_id, root_path)
        return scan_id

    async def cancel_scan(self, scan_id: str) -> bool:
        """Signal a running scan to stop after its current file."""
        if scan_id in self._cancel_events:
            self._cancel_events[scan_id].set()
            self._logger.info("Cancel signalled for scan %s", scan_id)
            return True
        return False

    def get_scan_status(self, scan_id: str) -> dict | None:
        """Return current progress for a scan, or None if unknown."""
        return self._active_scans.get(scan_id)

    def get_active_scans(self) -> dict[str, dict]:
        """Return copy of all active scan statuses."""
        return dict(self._active_scans)

    # ------------------------------------------------------------------
    # Internal: scan runner
    # ------------------------------------------------------------------

    async def _run_scan(
        self,
        scan_id: str,
        library_id: str,
        root_path: str,
        custom_extensions: list[str] | None,
        excluded_extensions: list[str] | None,
        included_fields: list[str] | None,
        job_id: str | None,
    ) -> None:
        """Step A 鈫?Step B 鈫?persist pipeline."""
        cancel = self._cancel_events.get(scan_id)
        if cancel is None:
            return

        # --- Status tracking ---
        status = {
            "scan_id": scan_id,
            "library_id": library_id,
            "stage": "discovering",
            "total": 0,
            "done": 0,
            "failed": 0,
            "cancelled": False,
            "elapsed": 0.0,
        }
        self._active_scans[scan_id] = status
        await self._publish_progress(scan_id, status)

        start_time = dt_mod.datetime.now(dt_mod.timezone.utc)

        try:
            # Step A.0: Quick skip if filesystem has not changed (scan cache)
            current_root_mtime = None
            try:
                _root = Path(root_path)
                if _root.exists():
                    current_root_mtime = _root.stat().st_mtime_ns
                if current_root_mtime is not None:
                    from ..models.library import Library as _LibChk
                    async with async_session_factory() as _chk_sess:
                        _chk_lib = await _chk_sess.get(_LibChk, uuid.UUID(library_id))
                        if _chk_lib and _chk_lib.settings:
                           _chk_cache = _chk_lib.settings.get("scan_cache")
                           if _chk_cache:
                               _chk_mtime = _chk_cache.get("root_mtime_ns")
                               _chk_count = _chk_cache.get("file_count")
                               if (_chk_mtime == current_root_mtime
                                       and _chk_count is not None
                                       and _chk_lib.total_assets == _chk_count):
                                   self._logger.info(
                                       "Scan cache hit - filesystem unchanged for %s "
                                       "(assets=%d, mtime match)",
                                       root_path, _chk_lib.total_assets)
                                   status["stage"] = "completed"
                                   status["done"] = 0
                                   status["total"] = 0
                                   status["elapsed"] = 0.0
                                   await self._publish_progress(scan_id, status)
                                   self._cleanup(scan_id)
                                   self._update_job_status(job_id, "completed", progress=100.0)
                                   return
            except Exception as _cache_e:
                self._logger.warning("Scan cache check failed (fallback to full scan): %s", _cache_e)
            discovered = await asyncio.to_thread(
                self._discover_files,
                root_path,
                custom_extensions,
                excluded_extensions,
            )
            if cancel.is_set():
                status["cancelled"] = True
                status["stage"] = "cancelled"
                await self._publish_progress(scan_id, status)
                self._cleanup(scan_id)
                self._update_job_status(job_id, "cancelled")
                return

            # -- Inline cache update helper --
            async def _update_scan_cache(_lib_id: str, _root: Path) -> None:
                'Store current root mtime + asset count into Library.settings.'
                try:
                    if _root.exists():
                        _mtime = _root.stat().st_mtime_ns
                        from ..models.library import Library as _LMod
                        from sqlalchemy import select as _Sel, func as _Func
                        from ..models.asset import Asset as _AMod
                        async with async_session_factory() as _uc_sess:
                           _uc_lib = await _uc_sess.get(_LMod, uuid.UUID(_lib_id))
                           if _uc_lib:
                               _uc_cnt = await _uc_sess.scalar(
                                   _Sel(_Func.count(_AMod.id)).where(
                                       _AMod.library_id == uuid.UUID(_lib_id)
                                   )
                               ) or 0
                               _uc_stg = dict(_uc_lib.settings or {})
                               _uc_stg["scan_cache"] = {
                                   "root_mtime_ns": _mtime,
                                   "file_count": _uc_cnt,
                                   "cached_at": dt_mod.datetime.now(
                                       dt_mod.timezone.utc
                                   ).isoformat(),
                               }
                               _uc_lib.settings = _uc_stg
                               await _uc_sess.commit()
                               self._logger.info(
                                   "Scan cache saved: %d assets, mtime=%s", _uc_cnt, _mtime)
                except Exception as _uce:
                    self._logger.warning("Failed to update scan cache: %s", _uce)

            # Step A.5: Incremental filter + Step A.6: Check-out (remove deleted files)
            try:
                from sqlalchemy import select as _sel
                from ..models.asset import Asset as _AssetModel
                async with async_session_factory() as _sess:
                    _rows = await _sess.execute(
                        _sel(_AssetModel.original_path).where(
                           _AssetModel.library_id == uuid.UUID(library_id)
                        )
                    )
                    _existing = {_row[0] for _row in _rows}
                    if _existing:
                        _before = len(discovered)
                        _on_disk = {f["path"] for f in discovered}
                        discovered = [f for f in discovered if f["path"] not in _existing]
                        self._logger.info(
                           "Incremental scan: %d existing skipped, %d new",
                           _before - len(discovered), len(discovered),
                        )

                        # Step A.6: Check-out 鈥?files in DB but no longer on disk
                        _gone = _existing - _on_disk
                        if _gone:
                           from sqlalchemy import delete as _sql_del
                           _del_result = await _sess.execute(
                               _sql_del(_AssetModel).where(
                                   _AssetModel.library_id == uuid.UUID(library_id),
                                   _AssetModel.original_path.in_(_gone),
                               )
                           )
                           await _sess.commit()
                           self._logger.info(
                               "Check-out: %d assets removed (files disappeared from disk)",
                               _del_result.rowcount)
            except Exception as e:
                self._logger.warning("Incremental / check-out fallback (full scan): %s", e)

            total = len(discovered)
            status["total"] = total
            status["stage"] = "probing"
            await self._publish_progress(scan_id, status)

            if total == 0:
                self._logger.info("No video files found in %s", root_path)
                status["stage"] = "completed"
                status["done"] = 0
                status["elapsed"] = (dt_mod.datetime.now(dt_mod.timezone.utc) - start_time).total_seconds()
                await self._publish_progress(scan_id, status)
                self._cleanup(scan_id)
                self._update_job_status(job_id, "completed", progress=100.0)
                await _update_scan_cache(library_id, Path(root_path))
                return

            # Step B 鈥?metadata probing with Semaphore control
            sem = _get_semaphore()
            batch_size = _scache.get_int("metadata_batch_size", settings.METADATA_BATCH_SIZE)
            probe_timeout = _scache.get_int("ffprobe_timeout", settings.FFPROBE_TIMEOUT)

            probe_results: list[dict] = []

            for i in range(0, total, batch_size):
                if cancel.is_set():
                    break

                batch = discovered[i:i + batch_size]
                batch_results = await self._probe_batch(
                    batch, sem, probe_timeout, included_fields
                )

                for r in batch_results:
                    if r["status"] == "ok":
                        probe_results.append(r["metadata"])
                        status["done"] += 1
                    elif r["status"] == "error":
                        status["failed"] += 1

                # Persist batch
                if probe_results:
                    new_assets = await self._batch_persist(library_id, probe_results)
                    for aid, vpath in new_assets:
                        asyncio.create_task(self._generate_thumbnail_task(aid, vpath))
                    probe_results.clear()

                status["elapsed"] = (dt_mod.datetime.now(dt_mod.timezone.utc) - start_time).total_seconds()
                await self._publish_progress(scan_id, status)

            # Flush remaining
            if probe_results:
                new_assets = await self._batch_persist(library_id, probe_results)
                for aid, vpath in new_assets:
                    asyncio.create_task(self._generate_thumbnail_task(aid, vpath))
                probe_results.clear()

            # Final status
            status["stage"] = "completed" if not cancel.is_set() else "cancelled"
            if cancel.is_set():
                status["cancelled"] = True
            status["elapsed"] = (dt_mod.datetime.now(dt_mod.timezone.utc) - start_time).total_seconds()
            await self._publish_progress(scan_id, status)

            self._update_job_status(
                job_id,
                "completed" if not cancel.is_set() else "cancelled",
                progress=100.0 if not cancel.is_set() else status["done"] / max(status["total"], 1) * 100,
            )

            # Update scan cache after successful full scan
            if not cancel.is_set():
                await _update_scan_cache(library_id, Path(root_path))
                self._logger.info(
                    "Scan completed (cache updated) - %s", root_path)

        except Exception as e:
            self._logger.exception("Scan %s failed: %s", scan_id, e)
            status["stage"] = "failed"
            status["error"] = str(e)[:500]
            await self._publish_progress(scan_id, status)
            self._update_job_status(job_id, "failed", error=str(e)[:500])

        finally:
            self._cleanup(scan_id)

    # ------------------------------------------------------------------
    # Step A: file discovery
    # ------------------------------------------------------------------

    def _discover_files(
        self,
        root_path: str,
        custom_extensions: list[str] | None,
        excluded_extensions: list[str] | None,
    ) -> list[dict]:
        """Walk directory tree and return dicts with path + file info."""
        path_obj = Path(root_path)
        if not path_obj.exists():
            self._logger.warning("Scan path does not exist: %s", root_path)
            return []

        # Convert custom_extensions to set[str]
        custom_set: set[str] | None = None
        if custom_extensions:
            custom_set = set(
                ext if ext.startswith(".") else f".{ext}"
                for ext in custom_extensions
            )

        excluded_set: set[str] | None = None
        if excluded_extensions:
            excluded_set = set(
                ext if ext.startswith(".") else f".{ext}"
                for ext in excluded_extensions
            )
        discovered: list[dict] = []
        for entry in scandir_walk(path_obj):
            if not entry.is_file(follow_symlinks=False):
                continue
            ext = Path(entry.name).suffix.lower()
            if not self._is_video_extension(ext, custom_set, excluded_set):
                continue
            try:
                st = entry.stat()
                discovered.append({
                    "path": entry.path,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                })
            except OSError:
                continue
        self._logger.info("Step A done: %d video files found in %s", len(discovered), root_path)
        return discovered

    @staticmethod
    def _is_video_extension(
        suffix: str,
        custom_extensions: set[str] | None,
        excluded_extensions: set[str] | None,
    ) -> bool:
        """Check if file extension is a supported video format."""
        # Use a local copy of supported extensions
        default_extensions = _scache.get_video_extensions()

        if excluded_extensions and suffix in excluded_extensions:
            return False

        if custom_extensions:
            return suffix in custom_extensions

        return suffix in default_extensions

    # ------------------------------------------------------------------
    # Step B: batch probing with Semaphore
    # ------------------------------------------------------------------

    async def _probe_batch(
        self,
        batch: list[dict],
        sem: asyncio.Semaphore,
        timeout: int = 120,
        included_fields: list[str] | None = None,
    ) -> list[dict]:
        """Probe a batch of files concurrently, Semaphore-limited."""
        async def _probe_one(item: dict) -> dict:
            path = item["path"]
            async with sem:
                try:
                    raw = await asyncio.wait_for(
                        probe_video_async(path),
                        timeout=timeout,
                    )
                    parsed = _raw_extract_metadata(raw)
                    meta = {}
                    meta.update(parsed.get("basic", {}))
                    meta.update(parsed.get("custom_metadata", {}))
                    # Flatten exif data for _extract_exif
                    _exif = parsed.get("exif", {})
                    if _exif.get("camera"):
                        for _k, _v in _exif["camera"].items():
                           meta["camera_" + _k] = str(_v) if not isinstance(_v, str) else _v
                    if _exif.get("gps"):
                        for _k, _v in _exif["gps"].items():
                           meta["gps_" + _k] = _v
                    meta["path"] = path
                    meta["file_size"] = item.get("size", 0)
                    if included_fields:
                        meta = _filter_metadata(parsed, set(included_fields))
                    return {"status": "ok", "metadata": meta}
                except asyncio.TimeoutError:
                    self._logger.warning("ffprobe timed out for %s", path)
                    return {"status": "error", "path": path, "error": "timeout"}
                except Exception as e:
                    self._logger.warning("ffprobe failed for %s: %s", path, e)
                    return {"status": "error", "path": path, "error": str(e)[:300]}

        tasks = [_probe_one(item) for item in batch]
        return await asyncio.gather(*tasks)    # ------------------------------------------------------------------
    # Batch DB persistence
    # ------------------------------------------------------------------

    async def _batch_persist(self, library_id: str, metas: list[dict]) -> list[tuple[str, str]]:
        """Upsert a batch of metadata results into PostgreSQL. Returns list of (asset_id, original_path)."""
        if not metas:
            return []

        created: list[tuple[str, str]] = []
        try:
            async with async_session_factory() as session:
                for meta in metas:
                    path = meta.get("video_path", meta.get("path", ""))
                    if not path:
                        continue
                    asset_id = str(uuid.uuid4())

                    # Build the UPSERT
                    stmt = (
                        _sql_text("""
                           INSERT INTO assets (
                               id, library_id, original_path, file_name, file_size,
                               width, height, duration, fps, codec,
                               video_bitrate, audio_codec, audio_channels, has_audio,
                               media_date, mime_type, exif, custom_metadata,
                               created_at, updated_at
                           ) VALUES (
                               :id, :library_id, :original_path, :file_name, :file_size,
                               :width, :height, :duration, :fps, :codec,
                               :video_bitrate, :audio_codec, :audio_channels, :has_audio,
                               :media_date, :mime_type, :exif, :custom_metadata,
                               NOW(), NOW()
                           )
                            ON CONFLICT (library_id, original_path)
                           DO UPDATE SET
                               width = EXCLUDED.width,
                               height = EXCLUDED.height,
                               duration = EXCLUDED.duration,
                               fps = EXCLUDED.fps,
                               codec = EXCLUDED.codec,
                               video_bitrate = EXCLUDED.video_bitrate,
                               audio_codec = EXCLUDED.audio_codec,
                               audio_channels = EXCLUDED.audio_channels,
                               has_audio = EXCLUDED.has_audio,
                               media_date = EXCLUDED.media_date,
                               mime_type = EXCLUDED.mime_type,
                               exif = EXCLUDED.exif,
                               custom_metadata = EXCLUDED.custom_metadata,
                               updated_at = NOW()
                        RETURNING id
                        """)
                    )

                    file_name = Path(path).name
                    media_date = meta.get("media_date")
                    if media_date and isinstance(media_date, str):
                        try:
                           media_date = dt_mod.datetime.fromisoformat(media_date)
                        except (ValueError, TypeError):
                           media_date = None

                    params = {
                        "id": asset_id,
                        "library_id": library_id,
                        "original_path": path,
                        "file_name": file_name,
                        "file_size": meta.get("file_size", 0) or 0,
                        "width": meta.get("width"),
                        "height": meta.get("height"),
                        "duration": meta.get("duration"),
                        "fps": meta.get("fps"),
                        "codec": meta.get("codec"),
                        "video_bitrate": meta.get("video_bitrate"),
                        "audio_codec": meta.get("audio_codec"),
                        "audio_channels": meta.get("audio_channels"),
                        "has_audio": meta.get("has_audio", False),
                        "media_date": media_date,
                        "mime_type": meta.get("mime_type", "video/mp4"),
                        "exif": json.dumps(_extract_exif(meta)) if _extract_exif(meta) else None,
                        "custom_metadata": json.dumps(_extract_custom_metadata(meta)) if _extract_custom_metadata(meta) else None,
                    }
                    result = await session.execute(stmt, params)
                    row = result.fetchone()
                    if row:
                        created.append((str(row[0]), path))

                # 鈹€鈹€ Bridge: create AIEngineJob rows for newly-imported assets 鈹€鈹€
                if created:
                    created_ids = [aid for aid, _ in created]
                    from app.core.job_helpers import insert_jobs_batch_async
                    created_rows = await insert_jobs_batch_async(session, created_ids)
                    self._logger.info(
                        "_batch_persist: created %d AIEngineJob rows for %d new assets",
                        created_rows, len(created),
                    )

                await session.commit()
        except Exception as e:
            self._logger.exception("Batch persist failed: %s", e)
        return created

    # ------------------------------------------------------------------
    # Thumbnail generation (fire-and-forget)
    # ------------------------------------------------------------------



    async def _generate_thumbnail_task(self, asset_id: str, video_path: str) -> None:
        """Generate thumbnail for a newly inserted asset. Fire-and-forget."""
        async with _get_thumbnail_semaphore():
            try:
                from ..core.transcoder import generate_asset_thumbnail
                loop = asyncio.get_running_loop()
                thumb_path = await asyncio.wait_for(
                    loop.run_in_executor(None, generate_asset_thumbnail, video_path, asset_id),
                    timeout=90.0,
                )

                async with async_session_factory() as session:
                    from ..models.asset import Asset
                    from sqlalchemy import select
                    stmt = select(Asset).where(Asset.id == asset_id)
                    result = await session.execute(stmt)
                    asset = result.scalar_one_or_none()
                    if asset and not asset.thumbnail_path:
                        asset.thumbnail_path = str(thumb_path)
                        await session.commit()
                        self._logger.info("Thumbnail generated for asset %s", asset_id)
            except asyncio.TimeoutError:
                self._logger.warning("Thumbnail generation timed out for %s", asset_id)
            except Exception as e:
                self._logger.warning("Thumbnail generation failed for %s: %s", asset_id, e)

    # ------------------------------------------------------------------
    # Progress / SSE
    # ------------------------------------------------------------------

    async def _publish_progress(self, scan_id: str, status: dict) -> None:
        """Publish scan progress to Redis pubsub channel."""
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            channel = f"scan:{scan_id}:progress"
            await r.publish(channel, json.dumps(status))
            await r.aclose()
        except ImportError:
            pass  # redis-py not available; skip pubsub
        except Exception as e:
            self._logger.debug("Redis pubsub publish fail: %s", e)

    def _update_job_status(
        self,
        job_id: str | None,
        status: str,
        progress: float = 0.0,
        error: str | None = None,
    ) -> None:
        """Update Job record in DB (runs in a sync helper thread)."""
        if not job_id:
            return

        def _do():
            try:
                from ..database import sync_session_factory as ssf
                session = ssf()
                job = session.query(Job).filter(Job.id == job_id).first()
                if job:
                    job.status = status
                    job.progress = progress
                    if error:
                        job.error = error
                    if status in ("completed", "failed", "cancelled"):
                        job.finished_at = dt_mod.datetime.now(dt_mod.timezone.utc)
                    session.commit()
                session.close()
            except Exception as e:
                self._logger.warning("Status update fail job=%s: %s", job_id, e)

        loop = asyncio.get_event_loop()
        try:
            if loop.is_running():
                asyncio.ensure_future(asyncio.to_thread(_do))
            else:
                loop.run_until_complete(asyncio.to_thread(_do))
        except Exception as e:
            self._logger.warning("Status update scheduling fail job=%s: %s", job_id, e)

    def _cleanup(self, scan_id: str) -> None:
        """Remove scan tracking data from memory."""
        self._active_scans.pop(scan_id, None)
        self._cancel_events.pop(scan_id, None)


# ============================================================================
# SSE / Redis progress helpers
# ============================================================================

class SSEManager:
    """Manages Server-Sent Events connections for scan progress."""

    def __init__(self):
        self._subscriptions: dict[str, set[asyncio.Queue]] = {}

    async def subscribe(self, scan_id: str) -> asyncio.Queue:
        """Create a queue for receiving progress updates for a scan."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscriptions.setdefault(scan_id, set()).add(q)
        return q

    def unsubscribe(self, scan_id: str, q: asyncio.Queue) -> None:
        """Remove a queue subscription."""
        subs = self._subscriptions.get(scan_id)
        if subs:
            subs.discard(q)

    async def publish(self, scan_id: str, data: dict) -> None:
        """Push data to all subscribers of a scan."""
        subs = self._subscriptions.get(scan_id, set())
        if not subs:
            return
        payload = json.dumps(data)
        dead: list[asyncio.Queue] = []
        for q in subs:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            subs.discard(q)

    async def listen_redis(self, scan_id: str, timeout: int = 3600) -> None:
        """
        Listen to Redis pubsub for a scan and forward to local subscribers.
        Run this as a background task alongside the scan.
        """
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"scan:{scan_id}:progress")
            dead = time.time() + timeout
            while time.time() < dead:
                try:
                    msg = await asyncio.wait_for(pubsub.get_message(timeout=1.0), timeout=2.0)
                except asyncio.TimeoutError:
                    if self._subscriptions.get(scan_id) is None or not self._subscriptions[scan_id]:
                        break
                    continue
                if msg and msg["type"] == "message":
                    try:
                        data = json.loads(msg["data"])
                    except json.JSONDecodeError:
                        continue
                    await self.publish(scan_id, data)
                    # Stop forwarding when scan completes
                    if data.get("stage") in ("completed", "failed", "cancelled"):
                        break
            await pubsub.unsubscribe()
            await pubsub.close()
            await r.aclose()
        except ImportError:
            pass
        except Exception as e:
            logger.warning("SSEManager.listen_redis error: %s", e)


# ============================================================================
# Helpers
# ============================================================================

def _extract_exif(meta: dict) -> dict:
    """Extract EXIF-like fields from ffprobe metadata."""
    exif = {}
    for key in ("gps_latitude", "gps_longitude", "gps_altitude",
                "camera_make", "camera_model", "lens_model"):
        if key in meta and meta[key] is not None:
            exif[key] = meta[key]
    return exif


def _extract_custom_metadata(meta: dict) -> dict:
    """Extract custom_metadata fields (everything not in basic/exif)."""
    basic_keys = {"width", "height", "fps", "codec", "duration", "media_date",
                  "video_bitrate", "audio_codec", "audio_channels", "has_audio",
                  "file_size", "file_name", "mime_type", "video_path", "path"}
    exif_keys = {"gps_latitude", "gps_longitude", "gps_altitude",
                 "camera_make", "camera_model", "lens_model"}
    skip = basic_keys | exif_keys
    return {k: v for k, v in meta.items() if k not in skip and v is not None}


# ============================================================================
# Disk file cleanup for asset deletion
# ============================================================================

def delete_asset_disk_files(asset, logger) -> dict:
    """Delete all disk files associated with an asset.

    Returns dict with 'deleted' (list of paths) and 'errors' (list of dicts).
    - original_path: only deleted if asset.is_imported is True
    - thumbnail_path, proxy_path, webvtt_path: deleted if set and exists
    - ClipSegment thumbnail_path (scene thumbnails): deleted if set and exists
    - Empty parent directories are cleaned up (up to 2 levels).
    """
    result: dict[str, list] = {"deleted": [], "errors": []}

    def _cleanup_empty_dir(dir_path, max_depth=2):
        current = dir_path
        depth = 0
        while current and depth < max_depth:
            try:
                if not current.exists():
                    current = current.parent
                    depth += 1
                    continue
                if any(current.iterdir()):
                    break
                current.rmdir()
                logger.debug("Removed empty directory: %s", current)
                current = current.parent
                depth += 1
            except (OSError, PermissionError):
                break

    def _safe_delete(path_str, label):
        if not path_str:
            return
        p = Path(path_str)
        if not p.exists():
            logger.debug("File not found (skip %s): %s", label, path_str)
            return
        try:
            p.unlink()
            result["deleted"].append(path_str)
            logger.info("Deleted disk file [%s]: %s", label, path_str)
            _cleanup_empty_dir(p.parent, max_depth=2)
        except Exception as e:
            result["errors"].append({"path": path_str, "error": str(e)})
            logger.error("Failed to delete [%s] %s: %s", label, path_str, e)

    # 1. Original video (only for imported assets)
    if getattr(asset, "is_imported", False):
        _safe_delete(getattr(asset, "original_path", None), "original")
    elif getattr(asset, "original_path", None):
        logger.warning(
            "Skipping original file deletion for non-imported asset %s: %s",
            getattr(asset, "id", "?"),
            asset.original_path,
        )

    # 2. Thumbnail
    _safe_delete(getattr(asset, "thumbnail_path", None), "thumbnail")

    # 3. Proxy video
    _safe_delete(getattr(asset, "proxy_path", None), "proxy")

    # 4. WebVTT subtitle
    _safe_delete(getattr(asset, "webvtt_path", None), "webvtt")

    # 5. Scene segment thumbnails
    segments = getattr(asset, "segments", []) or []
    for seg in segments:
        _safe_delete(getattr(seg, "thumbnail_path", None), "segment_thumbnail")

    return result


