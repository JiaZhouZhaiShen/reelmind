import os
import hashlib
import logging
from pathlib import Path
from typing import Callable, Iterator, Optional

from ..config import settings
from ..core.settings_cache import get_video_extensions as _get_video_extensions

logger = logging.getLogger(__name__)


def is_video_file(path: Path, custom_extensions: Optional[set[str]] = None, excluded_extensions: Optional[set[str]] = None) -> bool:
    """Check if a file is a video, optionally with custom include/exclude sets."""
    ext = path.suffix.lower()
    # If excluded, always exclude
    if excluded_extensions and ext in excluded_extensions:
        return False
    # Base + custom extensions
    base_extensions = _get_video_extensions()
    if custom_extensions:
        norm_custom = {e if e.startswith('.') else f'.{e}' for e in custom_extensions}
        base_extensions.update(norm_custom)
    return ext in base_extensions


def is_media_file(path: Path, custom_extensions: Optional[set[str]] = None, excluded_extensions: Optional[set[str]] = None) -> bool:
    """Only video files are media for ReelMind."""
    return is_video_file(path, custom_extensions, excluded_extensions)


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in settings.SUPPORTED_IMAGE_EXTENSIONS


def compute_file_hash(path: Path, chunk_size: int = 65536) -> str:
    logger.debug("Computing hash for %s (size=%d)", path, path.stat().st_size)
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
    hash_val = sha256.hexdigest()
    logger.debug("Hash for %s: %s", path, hash_val)
    return hash_val


def get_file_info(path: Path) -> dict:
    logger.debug("Getting file info for %s", path)
    stat = path.stat()
    info = {
        "path": str(path.resolve()),
        "file_name": path.name,
        "file_size": stat.st_size,
        "file_ctime": stat.st_ctime,
        "file_mtime": stat.st_mtime,
        "mime_type": _guess_mime(path),
    }
    logger.debug("File info for %s: size=%d, mime=%s", path, stat.st_size, info["mime_type"])
    return info


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    mime_map = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".m4v": "video/x-m4v",
        ".wmv": "video/x-ms-wmv",
        ".flv": "video/x-flv",
        ".ts": "video/mp2t",
        ".mts": "video/mp2t",
        ".m2ts": "video/mp2t",
        ".3gp": "video/3gpp",
        ".ogv": "video/ogg",
        ".mxf": "application/mxf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    return mime_map.get(ext, "application/octet-stream")


def scandir_walk(root: Path) -> Iterator[os.DirEntry]:
    """Fast recursive directory walk via os.scandir().

    On Windows NAS mounts (SMB/CIFS), os.scandir() uses FindFirstFile/FindNextFile
    which returns ALL entry metadata in one network round trip per directory,
    eliminating the per-file stat() calls that os.walk() and pathlib.rglob()
    each incur. This is dramatically faster on network filesystems with
    thousands of files spread across many directories.
    """
    stack = [root]
    while stack:
        dir_path = stack.pop()
        try:
            with os.scandir(str(dir_path)) as it:
                for entry in it:
                    yield entry
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
        except (PermissionError, OSError) as e:
            logger.warning("Skipping directory %s: %s", dir_path, e)


def scan_directory(path: Path, progress_callback: Callable | None = None, custom_extensions: Optional[list[str]] = None, excluded_extensions: Optional[list[str]] = None) -> list[dict]:
    logger.info("Scanning directory: %s", path)
    results = []
    if not path.exists():
        logger.warning("Path does not exist: %s", path)
        return results
    # Normalize extension sets once
    custom_set = set(custom_extensions or [])
    excluded_set = set(excluded_extensions or [])
    if custom_set:
        logger.info("Custom video extensions: %s", custom_set)
    if excluded_set:
        logger.info("Excluded extensions: %s", excluded_set)
    media_count = 0
    entry_count = 0
    for entry in scandir_walk(path):
        # Check for pause/cancel via callback every 2000 entries
        if progress_callback and entry_count > 0 and entry_count % 2000 == 0:
            try:
                cancel = progress_callback(entry_count, len(results))
                if cancel:
                    logger.info("Scan cancelled at %d entries, %d files", entry_count, len(results))
                    return results
            except Exception as e:
                logger.warning("Progress callback failed: %s", e)
        if entry.is_file(follow_symlinks=False):
            fpath = Path(entry.path)
            if is_video_file(fpath, custom_set, excluded_set):
                results.append(get_file_info(fpath))
                media_count += 1
        entry_count += 1
    logger.info("Scan complete: %s — %d media files found", path, media_count)
    return results
