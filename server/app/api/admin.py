"""Admin API 鈥?system settings, user management, job management."""

from __future__ import annotations

import uuid
import logging
from typing import Any
from pathlib import Path
import os, signal, threading

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.user import User
from ..models.job import Job
from ..models.asset import Asset
from ..models.system_settings import SystemSetting
from ..auth import get_current_user, hash_password
from ..config import settings as s

from ..core.indexer import get_metadata_field_definitions, ALL_METADATA_KEYS
 
logger = logging.getLogger(__name__)



_last_gpu_cache = {"ai_used": 0, "total_used": 0, "total": 0, "ai_percent": 0, "total_percent": 0}
_last_models_cache = {}

router = APIRouter(prefix="/admin", tags=["Admin"])

AI_SERVICE_URL = os.environ.get("AI_SERVICE_URL", "http://reelmind-ai:2589")


# 鈹€鈹€ Auth helper: admin-only dependency 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user


# 鈹€鈹€ System Settings CRUD 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "thumbnail_quality": {
        "value": "80", "value_type": "int",
        "category": "scanning",
        "description": "Thumbnail JPEG quality (1-100)",
    },
    "scan_interval_seconds": {
        "value": "300", "value_type": "int",
        "category": "scanning",
        "description": "Auto-scan interval in seconds (0=disabled)",
    },
    "supported_video_extensions": {
        "value": ".mp4,.mov,.avi,.mkv,.webm,.m4v,.wmv,.flv,.ts,.mts,.m2ts,.3gp,.ogv,.mxf", "value_type": "string",
        "category": "scanning",
        "description": "Comma-separated list of supported video file extensions",
    },
    "excluded_extensions": {
        "value": "", "value_type": "string",
        "category": "scanning",
        "description": "Comma-separated list of extensions to exclude from scanning",
    },
    "metadata_fields": {
        "value": "", "value_type": "string",
        "category": "indexing",
        "description": "Comma-separated list of metadata field keys to extract (empty = all fields)",
    },
    "ffprobe_concurrency": {
        "value": "4", "value_type": "int",
        "category": "indexing",
        "description": "Max parallel ffprobe processes for metadata extraction",
    },
    "metadata_batch_size": {
        "value": "50", "value_type": "int",
        "category": "indexing",
        "description": "Metadata results per batch DB commit",
    },
    "ffprobe_timeout": {
        "value": "120", "value_type": "int",
        "category": "indexing",
        "description": "Seconds before ffprobe times out on a single file",
    },
    "thumbnail_concurrency": {
        "value": "6", "value_type": "int",
        "category": "indexing",
        "description": "Max parallel ffmpeg processes for thumbnail generation",
    },
}


# 鈹€鈹€ Dashboard 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@router.get("/dashboard")
async def get_dashboard(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Admin dashboard summary statistics (single-query)."""
    from sqlalchemy import text
    row = (await session.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM assets) AS total_assets,
            (SELECT COALESCE(SUM(file_size), 0) FROM assets) AS total_size_bytes,
            (SELECT COALESCE(SUM(duration), 0.0) FROM assets) AS total_duration_seconds,
            (SELECT COUNT(*) FROM assets WHERE thumbnail_path IS NULL OR thumbnail_path = \'\') AS pending_import,
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*) FROM jobs WHERE status = \'running\') AS running_jobs,
            (SELECT COUNT(*) FROM jobs WHERE status = \'failed\') AS failed_jobs
    """))).one()
    return {
        "total_assets": row.total_assets,
        "total_size_bytes": row.total_size_bytes,
        "total_duration_seconds": float(row.total_duration_seconds),
        "pending_import": row.pending_import,
        "total_users": row.total_users,
        "running_jobs": row.running_jobs,
        "failed_jobs": row.failed_jobs,
    }


# 鈹€鈹€ System Status (Dashboard) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@router.get("/system-status")
async def get_system_status(
    _: dict = Depends(require_admin),
):
    """Aggregate system health for the admin dashboard:
    GPU usage and model load status from AI container.
    """
    import json
    from httpx import AsyncClient

    result: dict = {
        "gpu": {"ai_used": 0, "total_used": 0, "total": 0, "ai_percent": 0, "total_percent": 0},
        "models": {},
    }

    # Fetch GPU + model status from AI container
    global _last_gpu_cache, _last_models_cache
    try:
        async with AsyncClient(timeout=5) as client:
            h = await client.get(f"{AI_SERVICE_URL}/health")
            if h.status_code == 200:
                body = h.json()
                ai_used = body.get("memory_gb", 0)
                total_used = body.get("total_used_gb", ai_used)
                total = body.get("total_gb", 0)
                result["gpu"] = {
                    "ai_used": ai_used,
                    "total_used": total_used,
                    "total": total,
                    "ai_percent": round(ai_used / max(total, 1) * 100, 1),
                    "total_percent": round(total_used / max(total, 1) * 100, 1),
                }
                result["models"] = body.get("models", {})
                _last_gpu_cache = result["gpu"]
                _last_models_cache = result["models"]
    except Exception as e:
        logger.warning("Failed to fetch AI health: %s", e, exc_info=True)
        result["gpu"] = _last_gpu_cache
        result["models"] = _last_models_cache

    return result

@router.get("/settings")
async def list_admin_settings(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """List all system settings (DB values overlaid on defaults)."""
    rows = (await session.execute(select(SystemSetting))).scalars().all()
    db_map = {r.key: r for r in rows}
    result = {}
    for key, default in DEFAULT_SETTINGS.items():
        if key in db_map:
            result[key] = {
                "key": key,
                "value": db_map[key].value or default["value"],
                "value_type": db_map[key].value_type or default["value_type"],
                "category": db_map[key].category or default.get("category", "general"),
                "description": db_map[key].description or default["description"],
            }
        else:
            result[key] = {
                "key": key,
                "value": default["value"],
                "value_type": default["value_type"],
                "category": default.get("category", "general"),
                "description": default["description"],
            }
    return result


@router.put("/settings")
async def update_admin_settings(
    data: dict[str, str],
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Update multiple system settings at once."""
    updated = []
    for key, raw_value in data.items():
        if key not in DEFAULT_SETTINGS:
            logger.warning("Ignored unknown setting key '%s'", key)
            continue
        meta = DEFAULT_SETTINGS[key]
        value_type = meta["value_type"]
        try:
            _validate_value_type(raw_value, value_type)
        except ValueError as e:
            raise HTTPException(400, f"Invalid value for '{key}': {e}")
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        if setting is None:
            setting = SystemSetting(
                key=key,
                value=raw_value,
                value_type=value_type,
                category=meta.get("category", "general"),
                description=meta.get("description", ""),
            )
        else:
            setting.value = raw_value
        session.add(setting)
        updated.append(key)
    await session.commit()
    if updated:
        logger.info("Updated settings: %s", ", ".join(updated))
    # Reload settings cache so consumers pick up new values immediately
    from ..core import settings_cache
    await settings_cache.reload_all(session)
    return {"status": "ok", "updated": updated}


def _validate_value_type(raw: str, value_type: str) -> None:
    """Validate a raw string can be cast to the target type."""
    if value_type == "int":
        int(float(raw))
    elif value_type == "float":
        float(raw)
    elif value_type == "bool":
        if raw.lower() not in ("true", "false", "1", "0", "yes", "no"):
            raise ValueError("Expected boolean (true/false)")


# 鈹€鈹€ Logs 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@router.get("/logs")
async def list_log_files(
    _: dict = Depends(require_admin),
):
    """List log files in the LOG_DIR."""
    import os, stat
    log_dir = s.LOG_DIR
    log_path = Path(log_dir)
    if not log_path.exists():
        candidates = [
            Path(s.DATA_ROOT) / "logs",
            Path.cwd() / "logs",
            Path.home() / ".reelmind" / "logs",
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                log_path = c
                break
    if not log_path.exists():
        return {"directory": str(log_path), "files": []}
    files = []
    for f in sorted(log_path.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file() and f.suffix in (".log", ".txt", ".json"):
            files.append({
                "name": f.name,
                "size_bytes": f.stat().st_size,
                "modified_at": int(f.stat().st_mtime),
            })
    return {"directory": str(log_path), "files": files}


@router.get("/logs/{filename:path}")
async def view_log_file(
    filename: str,
    tail: int = Query(200),
    _: dict = Depends(require_admin),
):
    """Read the tail of a log file."""
    log_dir = s.LOG_DIR
    log_path = Path(log_dir).resolve()
    if not log_path.exists():
        candidates = [
            Path(s.DATA_ROOT).resolve() / "logs",
            Path.cwd().resolve() / "logs",
            Path.home().resolve() / ".reelmind" / "logs",
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                log_path = c.resolve()
                break

    # Resolve to canonical path — prevents directory traversal attacks
    file_path = (log_path / filename).resolve()

    # Security: ensure resolved path stays within the log directory subtree
    if not str(file_path).startswith(str(log_path) + os.sep) and str(file_path) != str(log_path):
        _logger.warning("Path traversal attempt blocked: %s", filename)
        raise HTTPException(status_code=403, detail="Access denied")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, f"Log file '{filename}' not found")
    allowed = (".log", ".txt", ".json")
    if file_path.suffix.lower() not in allowed:
        raise HTTPException(403, f"File type '{file_path.suffix}' not allowed")
    # Additional guard: refuse to read files larger than 100 MB
    max_size = 100 * 1024 * 1024
    if file_path.stat().st_size > max_size:
        raise HTTPException(status_code=413, detail="File too large")
    total_bytes = file_path.stat().st_size
    total_lines = 0
    lines = []
    truncated = False
    if total_bytes > 0:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            all_lines = fh.readlines()
        total_lines = len(all_lines)
        if tail > 0 and tail < total_lines:
            lines = all_lines[-tail:]
            truncated = True
        else:
            lines = all_lines
    return {
        "filename": filename,
        "lines": lines,
        "truncated": truncated,
        "total_lines": total_lines,
        "total_bytes": total_bytes,
    }

# 鈹€鈹€ Log Delete 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@router.delete("/logs/{filename:path}")
async def delete_log_file(
    filename: str,
    _: dict = Depends(require_admin),
):
    """Delete a single log file."""
    log_dir = s.LOG_DIR
    log_path = Path(log_dir)
    if not log_path.exists():
        candidates = [
            Path(s.DATA_ROOT) / "logs",
            Path.cwd() / "logs",
            Path.home() / ".reelmind" / "logs",
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                log_path = c
                break
    file_path = log_path / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, f'Log file "{filename}" not found')
    allowed = (".log", ".txt", ".json")
    if file_path.suffix not in allowed:
        raise HTTPException(403, f'File type "{file_path.suffix}" not allowed')
    try:
        file_path.unlink()
        logger.info("Deleted log file: %s", file_path)
        return {"status": "ok", "message": f'Deleted "{filename}"'}
    except Exception as e:
        logger.error("Failed to delete log file: %s", e)
        return {"status": "error", "message": str(e)}


@router.delete("/logs")
async def clear_all_logs(
    _: dict = Depends(require_admin),
):
    """Clear all log files."""
    log_dir = s.LOG_DIR
    log_path = Path(log_dir)
    if not log_path.exists():
        candidates = [
            Path(s.DATA_ROOT) / "logs",
            Path.cwd() / "logs",
            Path.home() / ".reelmind" / "logs",
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                log_path = c
                break
    if not log_path.exists():
        return {"status": "error", "message": "No log directory found"}
    deleted = []
    for f in log_path.iterdir():
        if f.is_file() and f.suffix in (".log", ".txt", ".json"):
            try:
                f.unlink()
                deleted.append(f.name)
            except Exception as e:
                logger.warning("Failed to delete '%s': %s", f.name, e)
    logger.info("Cleared %d log files", len(deleted))
    return {"status": "ok", "message": f"Cleared {len(deleted)} log files", "deleted": deleted}


