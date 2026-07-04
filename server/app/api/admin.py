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
    Docker container stats (CPU/Mem for server & AI),
    GPU usage and model load status from AI container.
    """
    import asyncio
    import json
    from httpx import AsyncClient

    result: dict = {
        "gpu": {"ai_used": 0, "total_used": 0, "total": 0, "ai_percent": 0, "total_percent": 0},
        "models": {},
        "containers": {},
    }

    async def _container_stats(name: str) -> dict | None:
        try:
            def _fetch():
                from .docker_api import DockerAPI
                d = DockerAPI()
                info = d.inspect_container(name)
                if not info:
                    return None
                status = info.get("State", {}).get("Status", "unknown")
                cid = info.get("Id", "")[:12]
                if not cid:
                    return {"status": status, "cpu_percent": 0, "memory_mb": 0, "memory_limit_mb": 0, "memory_percent": 0}
                code, raw = d._request("GET", f"/containers/{cid}/stats?stream=false")
                if code != 200 or not raw:
                    return {"status": status, "cpu_percent": 0, "memory_mb": 0, "memory_limit_mb": 0, "memory_percent": 0}
                s = json.loads(raw)
                cpu_stats = s.get("cpu_stats", {})
                precpu = s.get("precpu_stats", {})
                mem_stats = s.get("memory_stats", {})
                cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - precpu.get("cpu_usage", {}).get("total_usage", 0)
                sys_delta = cpu_stats.get("system_cpu_usage", 0) - precpu.get("system_cpu_usage", 0)
                online_cpus = cpu_stats.get("online_cpus", 1)
                cpu_pct = round((cpu_delta / max(sys_delta, 1)) * online_cpus * 100, 1) if sys_delta > 0 else 0
                mem_usage = mem_stats.get("usage", 0)
                mem_limit = mem_stats.get("limit", 1)
                mem_mb = round(mem_usage / 1024 / 1024, 1)
                mem_limit_mb = round(mem_limit / 1024 / 1024, 1)
                mem_pct = round(mem_usage / max(mem_limit, 1) * 100, 1)
                return {"status": status, "cpu_percent": cpu_pct, "memory_mb": mem_mb, "memory_limit_mb": mem_limit_mb, "memory_percent": mem_pct}
            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.warning("Failed to get stats for container '%s': %s", name, e)
            return {"status": "unknown", "cpu_percent": 0, "memory_mb": 0, "memory_limit_mb": 0, "memory_percent": 0, "error": str(e)[:80]}

    # Fetch container stats concurrently (was sequential before)
    server_res, ai_res = await asyncio.gather(
        _container_stats("reelmind-server"),
        _container_stats("reelmind-ai"),
    )
    result["containers"]["server"] = server_res
    result["containers"]["ai"] = ai_res

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
        raise HTTPException(404, f"Log file '{filename}' not found")
    allowed = (".log", ".txt", ".json")
    if file_path.suffix not in allowed:
        raise HTTPException(403, f"File type '{file_path.suffix}' not allowed")
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


