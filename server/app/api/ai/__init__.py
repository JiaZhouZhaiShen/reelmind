"""AI Task API — aggregate all sub-routers."""
from __future__ import annotations

from fastapi import APIRouter

from . import process, models, scan, pipeline, config, scan_events, pending_count

# Ensure start_event_scanner() runs on import (called at shared.py module level)
from . import shared  # noqa: F401

router = APIRouter(prefix="/ai", tags=["AI Processing"])

router.include_router(process.router)
router.include_router(models.router)
router.include_router(scan.router)
router.include_router(pipeline.router)
router.include_router(config.router)
# scan_events.router is registered separately in main.py (uses query-param token for SSE)
router.include_router(pending_count.router)
