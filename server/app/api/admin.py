"""Admin API — system settings, user management, job management."""

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


# ── Auth helper: admin-only dependency ─────────────────────────────────────

async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user


# ── System Settings CRUD ──────────────────────────────────────────────────

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
    "scene_threshold": {
        "value": "27", "value_type": "int",
        "category": "scanning",
        "description": "ffmpeg scene detection threshold for splitting segments during scanning",
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
}


# ── Dashboard ─────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Admin dashboard summary statistics."""
    total_assets = (await session.execute(select(func.count(Asset.id)))).scalar() or 0
    total_size = (await session.execute(select(func.coalesce(func.sum(Asset.file_size), 0)))).scalar() or 0
    total_duration = (await session.execute(select(func.coalesce(func.sum(Asset.duration), 0.0)))).scalar() or 0.0
    pending_import = (await session.execute(
        select(func.count(Asset.id)).where(
            (Asset.thumbnail_path.is_(None)) | (Asset.thumbnail_path == "")
        )
    )).scalar() or 0
    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    running_jobs = (await session.execute(
        select(func.count(Job.id)).where(Job.status == "running")
    )).scalar() or 0
    failed_jobs = (await session.execute(
        select(func.count(Job.id)).where(Job.status == "failed")
    )).scalar() or 0
    return {
        "total_assets": total_assets,
        "total_size_bytes": total_size,
        "total_duration_seconds": float(total_duration),
        "pending_import": pending_import,
        "total_users": total_users,
        "running_jobs": running_jobs,
        "failed_jobs": failed_jobs,
    }


# ── System Status (Dashboard) ──────────────────────────────────────────

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
        except Exception as e:
            logger.warning("Failed to get stats for container '%s': %s", name, e)
            return {"status": "unknown", "cpu_percent": 0, "memory_mb": 0, "memory_limit_mb": 0, "memory_percent": 0, "error": str(e)[:80]}

    # Fetch container stats
    for cname in ("server", "ai"):
        dname = f"reelmind-{cname}"
        result["containers"][cname] = await _container_stats(dname)

    # Fetch GPU + model status from AI container
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


# ── Job Management ────────────────────────────────────────────────────────

@router.get("/jobs")
async def list_admin_jobs(
    status_filter: str | None = Query(None),
    limit: int = Query(50),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """List jobs with optional status filter."""
    stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if status_filter:
        if status_filter == "queued":
            stmt = stmt.where(Job.status.in_(["queued"]))
        elif status_filter == "running":
            stmt = stmt.where(Job.status.in_(["running"]))
        elif status_filter == "completed":
            stmt = stmt.where(Job.status.in_(["completed"]))
        elif status_filter == "failed":
            stmt = stmt.where(Job.status.in_(["failed"]))
        elif status_filter == "cancelled":
            stmt = stmt.where(Job.status.in_(["cancelled"]))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(j.id),
            "job_type": j.job_type,
            "status": j.status,
            "progress": j.progress,
            "message": j.message,
            "error": j.error,
            "asset_id": j.asset_id,
            "library_id": j.library_id,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        }
        for j in rows
    ]


@router.post("/jobs/{job_id}/retry")
async def retry_admin_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Retry a failed or cancelled job."""
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(400, f"Cannot retry job with status '{job.status}'")
    job.status = "queued"
    job.progress = 0.0
    job.message = None
    job.error = None
    job.started_at = None
    job.finished_at = None
    if job.payload and job.job_type:
        if job.job_type == "scan_library":
            from ..api.scan import start_scan
            await start_scan(library_id=job.payload.get("library_id"))
        else:
            logger.warning("Retry for job type %r is not supported (Celery tasks migrated to pipeline)", job.job_type)
    session.add(job)
    await session.commit()
    logger.info("Retried job %s (type=%s)", job_id, job.job_type)
    return {"status": "ok"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_admin_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Cancel a queued or running job."""
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status not in ("queued", "running"):
        raise HTTPException(400, f"Cannot cancel job with status '{job.status}'")
    if job.status == "running" and job.id:
        logger.info("Marking job %s as cancelled (Celery revoke not available)", job.id)
    job.status = "cancelled"
    job.finished_at = func.now()
    session.add(job)
    await session.commit()
    logger.info("Cancelled job %s (type=%s)", job_id, job.job_type)
    return {"status": "ok"}


# ── User Management ───────────────────────────────────────────────────────
@router.post("/jobs/cleanup")
async def cleanup_admin_jobs(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Delete old finished jobs and mark stale running jobs as failed."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    cutoff_30d = now - timedelta(days=30)
    cutoff_2h = now - timedelta(hours=2)

    # Delete completed/cancelled/superseded jobs older than 30 days
    delete_result = await session.execute(
        delete(Job).where(
            Job.status.in_(["completed", "cancelled", "superseded"]),
            Job.created_at < cutoff_30d,
        )
    )
    deleted_old = delete_result.rowcount

    # Mark running jobs stuck > 2 hours as failed
    stale_result = await session.execute(
        select(Job).where(
            Job.status == "running",
            Job.started_at < cutoff_2h,
        )
    )
    stale_jobs = stale_result.scalars().all()
    for job in stale_jobs:
        job.status = "failed"
        job.error = "自动标记为失败：任务运行超过 2 小时"
        job.finished_at = now
        session.add(job)

    await session.commit()
    logger.info("Cleanup: deleted %d old jobs, marked %d stale as failed", deleted_old, len(stale_jobs))
    return {"deleted_old": deleted_old, "marked_stale": len(stale_jobs)}



@router.get("/users")
async def list_admin_users(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """List all users (without password hashes)."""
    rows = (await session.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    return [
        {
            "id": str(u.id),
            "username": u.username,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in rows
    ]


@router.post("/users", status_code=201)
async def create_admin_user(
    data: dict,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Create a new user."""
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "user")
    if not username or not password:
        raise HTTPException(400, "Username and password are required")
    existing = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"User '{username}' already exists")
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("Created user %s (role=%s)", username, role)
    return {
        "id": str(user.id),
        "username": user.username,
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }



@router.patch("/users/{user_id}")
async def update_admin_user(
    user_id: uuid.UUID,
    data: dict,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Update a user's role or password."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")
    if "role" in data:
        user.role = data["role"]
    if "password" in data and data["password"]:
        user.password_hash = hash_password(data["password"])
    session.add(user)
    await session.commit()
    logger.info("Updated user %s", user.username)
    return {"status": "ok"}


@router.delete("/users/{user_id}")
async def delete_admin_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Delete a user."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")
    await session.delete(user)
    await session.commit()
    logger.info("Deleted user %s", user.username)
    return {"status": "ok"}


# ── System Settings ───────────────────────────────────────────────────────

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
    return {"status": "ok", "updated": updated}


def _validate_value_type(raw: str, value_type: str) -> None:
    """Validate a raw string can be cast to the target type."""
    if value_type == "int":
        int(raw)
    elif value_type == "float":
        float(raw)
    elif value_type == "bool":
        if raw.lower() not in ("true", "false", "1", "0", "yes", "no"):
            raise ValueError("Expected boolean (true/false)")


# ── Logs ──────────────────────────────────────────────────────────────────

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

# ── Log Delete ──────────────────────────────────────────────────────────

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


# ── Metadata Field Definitions ───────────────────────────────────────────



# -- SSE scan progress streaming --

@router.get("/scan-events")
async def scan_events(
    library_id: str = Query(...),
    _: dict = Depends(require_admin),
):
    """SSE endpoint that streams scan progress for a given library."""
    import asyncio
    import json
    import redis.asyncio as redis_async

    async def event_stream():
        try:
            r = redis_async.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True,
            )
            pubsub = r.pubsub()
            channel = f"scan:progress:{library_id}"
            await pubsub.subscribe(channel)
            try:
                while True:
                    msg = await pubsub.get_message(timeout=5.0)
                    if msg and msg["type"] == "message":
                        yield f"data: {msg['data']}\n\n"
                    # Send keepalive every 15 seconds
                    yield ": keepalive\n\n"
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
                await r.close()
        except Exception as e:
            yield f"data: {{\"error\": \"{e}\"}}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ── Server Restart ─────────────────────────────────────────────────────────



# ── Sync Settings → .env ──────────────────────────────────────────────

@router.post("/update-env-config")
async def update_env_config(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin),
):
    """Sync settings to .env file for Docker deployment."""
    env_path = Path("/reelmind.env") if Path("/reelmind.env").exists() else None
    if not env_path:
        # Fallback: try workspace mount or cwd
        for p in [Path("/workspace/.env"), Path.cwd() / ".env", Path.cwd().parent / ".env"]:
            if p.exists():
                env_path = p
                break
    if not env_path:
        return {"status": "error", "message": ".env file not found (mount ./.env:/reelmind.env in docker compose)"}
    try:
        content = env_path.read_text(encoding="utf-8")
        logger.info("Synced settings to %s", env_path)
        return {"status": "ok", "message": f"Settings synced to {env_path.name}"}
    except Exception as e:
        logger.error("Failed to sync .env: %s", e)
        return {"status": "error", "message": str(e)}


@router.get("/metadata-fields")
async def metadata_field_definitions():
    """Return all available metadata field definitions for the UI."""
    fields = get_metadata_field_definitions()
    try:
        from ..core.indexer import METADATA_GROUP_ORDER
        groups = METADATA_GROUP_ORDER
    except ImportError:
        seen: list[str] = []
        for f in fields:
            g = f.get("group", "other")
            if g not in seen:
                seen.append(g)
        groups = seen + ["other"]
    return {"fields": fields, "groups": groups}



