import subprocess
import logging
from pathlib import Path

from ..config import settings

logger = logging.getLogger(__name__)


def generate_thumbnail(
    video_path: str | Path,
    output_path: str | Path,
    time_sec: float | None = None,
    size: tuple[int, int] | None = None,
) -> Path:
    logger.info(f"Generating thumbnail: {video_path} -> {output_path} (time={time_sec}, size={size})")
    if size is None:
        size = settings.THUMBNAIL_SIZE
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if time_sec is None:
        ffprobe = str(settings.FFMPEG_PATH).replace("ffmpeg", "ffprobe", 1) if "ffmpeg" in str(settings.FFMPEG_PATH).lower() else "ffprobe"
        probe_cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)]
        try:
            probe = subprocess.run(probe_cmd, capture_output=True, timeout=15, check=True)
            duration = float(probe.stdout.strip())
        except Exception:
            duration = 0
        if duration > 0:
            time_sec = max(0.5, min(duration * 0.3, 5.0))
            time_sec = min(time_sec, max(duration - 0.5, 0.5))
        else:
            time_sec = 1.0
        logger.debug("Auto-detected duration=%.2fs, using time_sec=%.2f", duration, time_sec)

    cmd = [
        settings.FFMPEG_PATH,
        "-y",
        "-ss", str(time_sec),
        "-analyzeduration", settings.FFPROBE_ANALYZE_DURATION,
        "-probesize", settings.FFPROBE_PROBE_SIZE,
        "-i", str(video_path),
        "-vframes", "1",
        "-s", f"{size[0]}x{size[1]}",
        "-q:v", str(settings.THUMBNAIL_QUALITY),
        str(out),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        logger.debug("Thumbnail generated: %s (size=%s)", output_path, size)
    except subprocess.CalledProcessError as e:
        logger.error("Thumbnail generation failed for %s: stderr=%s", video_path, e.stderr.decode() if e.stderr else "")
        raise
    return out

def generate_proxy_video(
    video_path: str | Path,
    output_path: str | Path,
    max_width: int | None = None,
    bitrate: str | None = None,
) -> Path:
    logger.info("Generating proxy video: %s → %s (max_width=%s, bitrate=%s)", video_path, output_path, max_width, bitrate)
    if max_width is None:
        max_width = settings.PROXY_VIDEO_MAX_WIDTH
    if bitrate is None:
        bitrate = settings.PROXY_VIDEO_BITRATE
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        settings.FFMPEG_PATH,
        "-y",
        "-i", str(video_path),
        "-vf", f"scale='min({max_width},iw)':-2",
        "-c:v", "libx264",
        "-b:v", bitrate,
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(out),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=600, check=True)
        logger.info("Proxy video generated: %s (max_width=%d, bitrate=%s, size=%d)",
                     output_path, max_width, bitrate, out.stat().st_size if out.exists() else 0)
    except subprocess.CalledProcessError as e:
        logger.error("Proxy generation failed for %s: stderr=%s", video_path, e.stderr.decode() if e.stderr else "")
        raise
    return out


def extract_frame(
    video_path: str | Path,
    output_path: str | Path,
    time_sec: float,
) -> Path:
    logger.debug("Extracting frame: %s → %s (time=%.1fs)", video_path, output_path, time_sec)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        settings.FFMPEG_PATH,
        "-y",
        "-ss", str(time_sec),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(out),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        logger.debug("Frame extracted: %s", output_path)
    except subprocess.CalledProcessError as e:
        logger.error("Frame extraction failed for %s @%.1fs: stderr=%s", video_path, time_sec, e.stderr.decode() if e.stderr else "")
        raise
    return out
def generate_asset_thumbnail(
    video_path: str | Path,
    asset_id: str,
    output_dir: str | Path | None = None,
    time_sec: float | None = None,
) -> Path:
    """Generate an asset poster thumbnail.

    Pure function: ffmpeg -> JPG. No DB, no Celery.
    Output: {output_dir}/{asset_id[:2]}/{asset_id}.jpg
    Idempotent: returns existing path if file already exists.
    """
    _dir = Path(output_dir) if output_dir else settings.CACHE_ROOT / "thumbnails"
    subdir = _dir / asset_id[:2]
    out_path = subdir / f"{asset_id}.jpg"

    if out_path.exists():
        logger.debug("Thumbnail already exists: %s", out_path)
        return out_path

    return generate_thumbnail(video_path, out_path, time_sec=time_sec)

