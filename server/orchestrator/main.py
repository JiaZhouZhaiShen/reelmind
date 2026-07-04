"""ReelMind Orchestrator — API-driven polling scheduler for AI engine jobs."""
from __future__ import annotations

import datetime
import json
import logging
import os
import sys
import time
import uuid
import urllib.request
import zoneinfo

POLL_INTERVAL = int(os.environ.get("ORCHESTRATOR_POLL_INTERVAL", "5"))
JOB_TIMEOUT_MINUTES = int(os.environ.get("ORCHESTRATOR_JOB_TIMEOUT", "180"))
MAX_RETRIES = int(os.environ.get("ORCHESTRATOR_MAX_RETRIES", "3"))
AI_SERVICE_URL = os.environ.get("ORCHESTRATOR_AI_URL", "http://reelmind-ai:2589")
SERVER_URL = os.environ.get("ORCHESTRATOR_SERVER_URL", "http://reelmind-server:2588")
TIMEZONE = os.environ.get("ORCHESTRATOR_TIMEZONE", "Asia/Shanghai")

ENGINES = ("scene", "yolo", "ocr", "clip", "transcript", "diarization")
ENGINE_DEPENDS = {
    "scene": (),
    "yolo": ("scene",),
    "ocr": ("scene",),
    "clip": ("scene",),
    "transcript": (),
    "diarization": ("transcript",),

}

logger = logging.getLogger("orchestrator")


def _server_get(path: str) -> dict | None:
    """GET Server API."""
    try:
        req = urllib.request.Request(f"{SERVER_URL}/api{path}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.warning("Server GET %s failed: %s", path, e)
        return None


def _server_post(path: str, data: dict | None = None) -> dict | None:
    """POST Server API."""
    try:
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(
            f"{SERVER_URL}/api{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.warning("Server POST %s failed: %s", path, e)
        return None


def _recover_stale() -> int:
    """通过 Server API 恢复超时/耗尽重试次数的 jobs."""
    result = _server_post("/ai/pipeline/auto/recover-stale", {})
    if result:
        recovered = result.get("recovered", 0)
        exhausted = result.get("exhausted", 0)
        if recovered:
            logger.info("Recovered %d stale jobs for retry", recovered)
        if exhausted:
            logger.warning("Exhausted %d jobs (max retries=%d)", exhausted, MAX_RETRIES)
        return recovered + exhausted
    return 0


def _log_pending_summary() -> int:
    """通过 Server API 获取 pending 汇总."""
    result = _server_get("/ai/pipeline/auto/pending-summary")
    if result:
        total = result.get("total_pending", 0)
        per_engine = result.get("pending_per_engine", {})
        if total:
            parts = ", ".join(f"{k}={v}" for k, v in sorted(per_engine.items()))
            logger.info("Pending: %d total [%s]", total, parts)
        return total
    return 0


def _get_auto_config() -> dict | None:
    """通过 Server API 读取 auto pipeline 配置."""
    result = _server_get("/ai/pipeline/auto/config")
    if result:
        return result.get("config")
    return None


def _check_auto_conditions(config: dict) -> bool:
    """全 API 方式检查 auto 条件（不直连 PG）。"""
    if not config.get("enabled", False):
        return False
    start_h = config.get("time_window_start", 0)
    end_h = config.get("time_window_end", 6)
    tz = zoneinfo.ZoneInfo(TIMEZONE)
    current_hour = datetime.datetime.now(tz).hour
    if start_h <= end_h:
        if not (start_h <= current_hour < end_h):
            return False
    else:
        if not (current_hour >= start_h or current_hour < end_h):
            return False
    summary = _server_get("/ai/pipeline/auto/pending-summary")
    if not summary:
        return False
    if summary.get("backlog", 0) == 0:
        return False
    if summary.get("running", 0) > 0:
        return False
    gpu_threshold = config.get("gpu_threshold_percent", 50)
    try:
        req = urllib.request.Request(f"{AI_SERVICE_URL}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read())
            total_gb = body.get("total_gb", 0) or 1
            total_used = body.get("total_used_gb", 0)
            total_pct = total_used / total_gb * 100
            if total_pct > gpu_threshold:
                logger.info(
                    "GPU at %.0f%% > threshold %d%%, waiting",
                    total_pct, gpu_threshold,
                )
                return False
    except Exception as e:
        logger.warning("Failed to check GPU health: %s", e)
        return False
    return True


def _run_auto_schedule():
    """全 API 方式：读配置 → 检查条件 → claim → 等完成 → 下一轮."""
    while True:
        # Re-read config each cycle so user changes take effect immediately
        config = _get_auto_config()
        if not config:
            break
        if not _check_auto_conditions(config):
            logger.info("Auto-schedule: conditions no longer met, pausing")
            break
        engines = config.get("engines", list(ENGINES))
        batch_size = config.get("batch_size", 50)
        timeout_min = config.get("timeout_minutes", 180)
        logger.info(
            "Auto-schedule: conditions met (time_window=%d-%d, batch_size=%d, engines=%s)",
            config.get("time_window_start", 0),
            config.get("time_window_end", 6),
            batch_size,
            engines,
        )
        result = _server_post("/ai/pipeline/auto/claim", {
            "engines": engines,
            "batch_size": batch_size,
            "filters": config.get("filters", {}),
        })
        if not result or not result.get("claimed"):
            logger.info("Auto-schedule: no pending videos to claim")
            break
        media_ids = result["media_ids"]
        batch_id = result["batch_id"]
        logger.info("Auto-schedule: claimed %d videos, batch=%s", len(media_ids), batch_id)
        wait_poll_count = 0
        deadline = time.time() + timeout_min * 60
        consecutive_fail = 0
        while time.time() < deadline:
            status = _server_get(f"/ai/pipeline/auto/chunk-done?batch_id={batch_id}")
            if status and status.get("done"):
                remaining = status.get("remaining", 0)
                if remaining == 0:
                    logger.info("Auto-schedule: chunk %s completed", batch_id)
                    break
            try:
                req = urllib.request.Request(f"{SERVER_URL}/api/ping", method="GET")
                with urllib.request.urlopen(req, timeout=3): pass
                req2 = urllib.request.Request(f"{AI_SERVICE_URL}/health", method="GET")
                with urllib.request.urlopen(req2, timeout=3): pass
                consecutive_fail = 0
            except Exception as e:
                consecutive_fail += 1
                if consecutive_fail >= 2:
                    logger.warning(
                        "Service unreachable after %d checks (%s)",
                        consecutive_fail, e,
                    )
                    logger.info("Auto-schedule: services unreachable, reclaiming batch=%s", batch_id)
                    _server_post("/ai/pipeline/auto/reclaim", {
                        "media_ids": media_ids,
                        "engines": engines,
                    })
                    break
            time.sleep(10)
            wait_poll_count += 1
            if wait_poll_count % 3 == 0:  # every ~30s, re-check auto enabled
                current_config = _get_auto_config()
                if current_config and not current_config.get("enabled", False):
                    logger.info("Auto-schedule: auto disabled during chunk wait, reclaiming batch=%s", batch_id)
                    _server_post("/ai/pipeline/auto/reclaim", {
                        "media_ids": media_ids,
                        "engines": engines,
                    })
                    break
        else:
            logger.warning("Auto-schedule: chunk timed out batch=%s", batch_id)
            _server_post("/ai/pipeline/auto/reclaim", {
                "media_ids": media_ids,
                "engines": engines,
            })
            break
    _log_pending_summary()
def _run_loop():
    """Main orchestration loop (all via Server API, no direct PG)."""
    logger.info(
        "Orchestrator started (API mode, poll=%ds timeout=%dmin max_retries=%d)",
        POLL_INTERVAL, JOB_TIMEOUT_MINUTES, MAX_RETRIES,
    )
    cycle = 0
    while True:
        cycle += 1
        try:
            changed = _recover_stale()
            pending = _log_pending_summary()
            if pending > 0:
                cfg = _get_auto_config()
                if cfg and cfg.get("enabled", False):
                    _run_auto_schedule()
        except Exception:
            logger.exception("Cycle %d failed", cycle)
        # Use check_interval_seconds from auto config if available
        config = _get_auto_config()
        if config and config.get("check_interval_seconds", 0) > 0:
            cycle_interval = config["check_interval_seconds"]
        else:
            cycle_interval = POLL_INTERVAL
        time.sleep(cycle_interval)

from log_setup import setup_logging


def main():
    setup_logging()
    _run_loop()


if __name__ == "__main__":
    main()

