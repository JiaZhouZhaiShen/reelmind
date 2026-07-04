"""ReelMind - AI-Powered Video Library Management."""

from __future__ import annotations
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.responses import FileResponse

from .config import settings, ensure_dirs
from .core.log_setup import setup_logging, AccessLogMiddleware
from .database import init_db, close_db

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize logging first
    setup_logging(
        log_dir=settings.LOG_DIR,
        level=settings.LOG_LEVEL,
        log_max_bytes=settings.LOG_MAX_BYTES,
        log_backup_count=settings.LOG_BACKUP_COUNT,
        enable_access_log=settings.ENABLE_ACCESS_LOG,
    )
    _logger = logging.getLogger("reelmind")
    _logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    ensure_dirs()
    await init_db()
    _logger.info("Database initialised - %s", settings.DATABASE_URL.replace(settings.DB_PASSWORD, "****"))

    # Load system settings into in-memory cache
    from .core import settings_cache as _settings_cache
    await _settings_cache.load_all()
    _logger.info("System settings cache loaded")

    # Check for interrupted batch checkpoints (server restart recovery)
    try:
        from app.database import sync_session_factory
        from app.models.batch_checkpoint import BatchCheckpoint
        from app.core.job_helpers import reset_stale_jobs
        from datetime import datetime, timedelta, timezone
        session = sync_session_factory()
        running_cps = session.query(BatchCheckpoint).filter(
            BatchCheckpoint.status == "running"
        ).all()
        stale_count = 0
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        for cp in running_cps:
            if cp.created_at and cp.created_at < cutoff and cp.processed < cp.total_videos:
                chunk_ids = cp.current_chunk_ids or []
                if chunk_ids:
                    try:
                        job_reset_count = reset_stale_jobs(session, chunk_ids)
                    except Exception:
                        _logger.exception("Failed to reset engine jobs for stale checkpoint %s", cp.id)
                cp.status = "failed"
                stale_count += 1
        if job_reset_count > 0:
            _logger.warning(
                "Reset %d stuck running engine jobs back to pending for %d stale checkpoint(s)",
                job_reset_count, stale_count,
            )
        session.commit()
        if stale_count > 0:
            _logger.warning("Auto-marked %d stale running checkpoints as failed", stale_count)
        elif running_cps:
            _logger.warning(
                "Found %d recent running checkpoints - these may still be active", len(running_cps)
            )
        else:
            _logger.info("No stale checkpoints found")
        session.close()
    except Exception as e:
        _logger.warning("Could not check batch checkpoints: %s", e)

    # --- Periodic background auto-scan ---
    _periodic_scan_task = None
    try:
        from .api.scan import trigger_library_scan
        from .database import async_session_factory
        from .models.library import Library
        from .models.system_settings import SystemSetting
        from sqlalchemy import select

        async def _periodic_scan_loop():
            _logger.info("Periodic auto-scan loop initialized")
            await asyncio.sleep(30)
            while True:
                try:
                    # Read scan interval from DB
                    async with async_session_factory() as session:
                        rows = (await session.execute(select(SystemSetting).where(
                            SystemSetting.key == "scan_interval_seconds"
                        ))).scalars().all()
                    interval = int(rows[0].value) if rows else 300
                    await asyncio.sleep(interval)
                    async with async_session_factory() as session:
                        result = await session.execute(
                            select(Library).where(Library.auto_scan == True)
                        )
                        libs = result.scalars().all()
                    for lib in libs:
                        try:
                            await trigger_library_scan(str(lib.id), purge=True)
                        except Exception as e:
                            _logger.warning("Auto-scan error for library %s: %s", lib.id, e)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    _logger.error("Periodic scan loop error: %s", e)
            _logger.info("Periodic auto-scan stopped")

        _periodic_scan_task = asyncio.create_task(_periodic_scan_loop())
        _logger.info("Periodic auto-scan background task created")
    except Exception as e:
        _logger.warning("Could not start periodic auto-scan: %s", e)
    yield
    _logger.info("Shutting down %s", settings.APP_NAME)
    if _periodic_scan_task:
        _periodic_scan_task.cancel()
        _logger.info("Periodic auto-scan task cancelled")
    await close_db()


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

# ── Middleware stack (order matters: access log first) ────────────────
app.add_middleware(AccessLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api import assets, assets_detail, assets_browse, assets_repair, libraries, search, preview, system
from .api import auth
from .api import tags
from .api import admin_logs
from .api import admin, admin_jobs, admin_users, admin_extras
from .api import ai
from .api import scan
app.include_router(assets.router, prefix=settings.API_PREFIX)
app.include_router(assets_browse.router, prefix=settings.API_PREFIX)
app.include_router(assets_detail.router, prefix=settings.API_PREFIX)
app.include_router(assets_repair.router, prefix=settings.API_PREFIX)
app.include_router(libraries.router, prefix=settings.API_PREFIX)
app.include_router(search.router, prefix=settings.API_PREFIX)
app.include_router(preview.router, prefix=settings.API_PREFIX)
app.include_router(system.router, prefix=settings.API_PREFIX)
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(tags.router, prefix=settings.API_PREFIX)
app.include_router(admin_logs.router, prefix=settings.API_PREFIX)
app.include_router(admin.router, prefix=settings.API_PREFIX)
app.include_router(admin_jobs.router, prefix=settings.API_PREFIX)
app.include_router(admin_users.router, prefix=settings.API_PREFIX)
app.include_router(admin_extras.router, prefix=settings.API_PREFIX)
app.include_router(ai.router, prefix=settings.API_PREFIX)
app.include_router(scan.router, prefix=settings.API_PREFIX)


@app.get(settings.API_PREFIX + "/ping")
async def ping():
    return {"status": "pong", "app": settings.APP_NAME, "version": settings.APP_VERSION}


# ── Frontend static files ──────────────────────────────────────────────
frontend_candidates = [
    Path(settings.FRONTEND_DIST),        # from env var or default
    Path("/web/dist"),                    # Docker volume mount
    BASE_DIR / "web" / "dist",            # dev mode relative path (wrong)
    BASE_DIR.parent / "web" / "dist",  # correct dev mode path
]
for fd in frontend_candidates:
    resolved = fd.resolve()
    if resolved.exists() and resolved.is_dir():
        _frontend_path = resolved
        break
else:
    _frontend_path = None

if _frontend_path:
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = _frontend_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_path / "index.html"))
