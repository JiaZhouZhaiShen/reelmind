"""ReelMind Orchestrator — lightweight polling scheduler for AI engine jobs.

P3: Pure PG auto-scheduling loop (no HTTP, no volumes).

Flow per cycle:
  1. Recover stale timed-out jobs (existing)
  2. Log pending summary (existing)
  3. Auto-schedule: read PG config → check conditions → claim chunk → write event → wait → loop
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
import time
import uuid
import json
import urllib.request
import zoneinfo

import psycopg2
import psycopg2.extras
import psycopg2.pool

# ── config ───────────────────────────────────────────────────────────────────

POLL_INTERVAL = int(os.environ.get("ORCHESTRATOR_POLL_INTERVAL", "5"))  # fallback; _run_loop uses PG config check_interval_seconds when available
JOB_TIMEOUT_MINUTES = int(os.environ.get("ORCHESTRATOR_JOB_TIMEOUT", "180"))
MAX_RETRIES = int(os.environ.get("ORCHESTRATOR_MAX_RETRIES", "3"))
AI_SERVICE_URL = os.environ.get("ORCHESTRATOR_AI_URL", "http://reelmind-ai:2589")
SERVER_SERVICE_URL = os.environ.get("ORCHESTRATOR_SERVER_URL", "http://reelmind-server:2588")

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

DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_USER = os.environ.get("DB_USER", "reelmind")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "reelmind")
DB_NAME = os.environ.get("DB_NAME", "reelmind")

logger = logging.getLogger("orchestrator")

# ── connection pool ─────────────────────────────────────────────────────────

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_conn():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=2,
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME,
        )
    return _pool.getconn()


def _put_conn(conn):
    if _pool:
        _pool.putconn(conn)


# ═════════════════════════════════════════════════════════════════════════════
# Existing SQL — timeout / backlog
# ═════════════════════════════════════════════════════════════════════════════

_RECOVER_STALE = """
    UPDATE ai_engine_jobs
    SET status = 'pending',
        retry_count = retry_count + 1,
        started_at = NULL,
        completed_at = NULL,
        error_message = CASE
            WHEN retry_count >= %(max_retries)s THEN 'timeout after ' || %(timeout)s::text || ' min'
            ELSE 'timeout, retrying'
        END
    WHERE status = 'running'
      AND started_at < NOW() - (%(timeout)s || ' minutes')::interval
      AND retry_count < %(max_retries)s
    RETURNING media_id, engine_name, retry_count
"""

_RECOVER_EXHAUSTED = """
    UPDATE ai_engine_jobs
    SET status = 'error',
        started_at = NULL,
        completed_at = NOW(),
        error_message = 'exhausted retries after timeout'
    WHERE status = 'running'
      AND started_at < NOW() - (%(timeout)s || ' minutes')::interval
      AND retry_count >= %(max_retries)s
    RETURNING media_id, engine_name
"""

_COUNT_PENDING = """
    SELECT engine_name, COUNT(*) AS cnt
    FROM ai_engine_jobs
    WHERE status = 'pending'
    GROUP BY engine_name
    ORDER BY engine_name
"""

_CHECK_BACKLOG = """
    SELECT COUNT(*) FROM ai_engine_jobs
    WHERE status = 'pending'
      AND NOT EXISTS (
          SELECT 1 FROM ai_engine_jobs d
          WHERE d.media_id = ai_engine_jobs.media_id
            AND d.engine_name = ANY(ai_engine_jobs.depends_on)
            AND d.status != 'completed'
      )
"""

_CHECK_RUNNING_BATCH = """
    SELECT COUNT(*) FROM ai_engine_jobs
    WHERE status = 'running'
"""


# ═════════════════════════════════════════════════════════════════════════════
# P3: Auto-scheduling SQL
# ═════════════════════════════════════════════════════════════════════════════

_GET_AUTO_CONFIG = """
    SELECT config FROM pipeline_configs
    WHERE name = 'auto'
"""

_CLAIM_CHUNK = """
    WITH eligible_media AS (
        SELECT DISTINCT j.media_id
        FROM ai_engine_jobs j
        JOIN assets a ON a.id = j.media_id
        WHERE j.status = 'pending'
          AND j.engine_name = ANY(%(engines)s::varchar[])
          AND NOT EXISTS (
              SELECT 1 FROM ai_engine_jobs d
              WHERE d.media_id = j.media_id
                AND d.engine_name = ANY(j.depends_on)
                AND d.status != 'completed'
          )
          AND (%(max_file_size_bytes)s <= 0 OR a.file_size IS NULL OR a.file_size <= %(max_file_size_bytes)s)
          AND (%(max_duration_seconds)s <= 0 OR a.duration IS NULL OR a.duration <= %(max_duration_seconds)s)
        ORDER BY j.media_id
        LIMIT %(batch_size)s
    ),
    eligible AS (
        SELECT j.media_id
        FROM ai_engine_jobs j
        WHERE j.media_id IN (SELECT media_id FROM eligible_media)
          AND j.status = 'pending'
          AND j.engine_name = ANY(%(engines)s::varchar[])
        FOR UPDATE OF j SKIP LOCKED
    )
    UPDATE ai_engine_jobs
    SET status = 'running',
        started_at = NOW(),
        retry_count = 0,
        error_message = NULL
    FROM eligible
    WHERE ai_engine_jobs.media_id = eligible.media_id
      AND ai_engine_jobs.status = 'pending'
      AND ai_engine_jobs.engine_name = ANY(%(engines)s::varchar[])
    RETURNING ai_engine_jobs.media_id
"""

_CHECK_CHUNK_DONE = """
    SELECT COUNT(*) AS remaining
    FROM ai_engine_jobs
    WHERE media_id = ANY(%(media_ids)s::uuid[])
      AND engine_name = ANY(%(engines)s::varchar[])
      AND status NOT IN ('completed', 'error', 'cancelled')
"""

_NOTIFY_EVENT = """
    INSERT INTO orchestration_events (event_type, batch_id, data)
    VALUES (%(event_type)s, %(batch_id)s, %(data)s::jsonb)
"""

# ═════════════════════════════════════════════════════════════════════════════
# Core helpers
# ═════════════════════════════════════════════════════════════════════════════

def _recover_stale(conn):
    """Reset timed-out running jobs back to pending (or error if exhausted)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            _RECOVER_STALE,
            {"timeout": JOB_TIMEOUT_MINUTES, "max_retries": MAX_RETRIES},
        )
        recovered = cur.fetchall()
        if recovered:
            logger.info("Recovered %d stale jobs for retry", len(recovered))
            for row in recovered:
                logger.info("  %s/%s retry=%d", row["media_id"][:8], row["engine_name"], row["retry_count"])

        cur.execute(
            _RECOVER_EXHAUSTED,
            {"timeout": JOB_TIMEOUT_MINUTES, "max_retries": MAX_RETRIES},
        )
        exhausted = cur.fetchall()
        if exhausted:
            logger.warning("Exhausted %d jobs (max retries=%d)", len(exhausted), MAX_RETRIES)
            for row in exhausted:
                logger.warning("  %s/%s → error", row["media_id"][:8], row["engine_name"])
        conn.commit()
        return len(recovered) + len(exhausted)


def _log_pending_summary(conn):
    """Log current pending counts per engine."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(_COUNT_PENDING)
        rows = cur.fetchall()
        counts = {r["engine_name"]: r["cnt"] for r in rows}
        total = sum(counts.values())
        if total:
            parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            logger.info("Pending: %d total [%s]", total, parts)
        return total


def _get_auto_config(conn):
    """Read auto pipeline config from PG pipeline_configs table."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(_GET_AUTO_CONFIG)
        row = cur.fetchone()
        if not row:
            return None
        return row["config"]


def _check_auto_conditions(conn, config: dict) -> bool:
    """Check if auto-scheduling conditions are met.

    Conditions:
    1. config.enabled == true
    2. Current hour within [time_window_start, time_window_end)
    3. No active running batch
    4. Has backlog of ready-to-process pending jobs
    5. GPU total usage below gpu_threshold_percent
    """
    # 1. Enabled
    if not config.get("enabled", False):
        return False

    # 2. Time window
    if config.get("time_window_start", 0) == 0 and config.get("time_window_end", 6) == 23:
        pass  # 0-23 means all 24 hours
    else:
        tz = zoneinfo.ZoneInfo(TIMEZONE)
        now = datetime.datetime.now(tz)
        current_hour = now.hour
        start_h = config.get("time_window_start", 0)
        end_h = config.get("time_window_end", 6)
        if start_h <= end_h:
            if not (start_h <= current_hour < end_h):
                return False
        else:
            # Wraparound (e.g. 22-4 means 22:00 to 04:00 next day)
            if not (current_hour >= start_h or current_hour < end_h):
                return False

    # 3. No active running batch
    with conn.cursor() as cur:
        cur.execute(_CHECK_RUNNING_BATCH)
        if cur.fetchone()[0] > 0:
            return False

    # 4. Has backlog
    with conn.cursor() as cur:
        cur.execute(_CHECK_BACKLOG)
        if cur.fetchone()[0] == 0:
            return False

    # 5. GPU usage below threshold
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
                    "Auto-schedule: GPU at %.0f%% > threshold %d%%, waiting",
                    total_pct, gpu_threshold,
                )
                return False
    except Exception as e:
        logger.warning("Auto-schedule: failed to check GPU health: %s", e)
        # If AI container is unreachable or health check fails,
        # don't start auto-schedule (conservative)
        return False

    return True


def _claim_next_chunk(conn, config: dict) -> tuple[list[str], str]:
    """Atomically claim a chunk of pending jobs (FOR UPDATE SKIP LOCKED).

    Returns (media_ids, batch_id).
    """
    engines = config.get("engines", list(ENGINES))
    batch_size = config.get("batch_size", 50)
    filters = config.get("filters", {})
    max_file_size_mb = filters.get("max_file_size_mb", 0)
    max_duration_minutes = filters.get("max_duration_minutes", 0)
    max_file_size_bytes = max_file_size_mb * 1024 * 1024 if max_file_size_mb > 0 else 0
    max_duration_seconds = max_duration_minutes * 60 if max_duration_minutes > 0 else 0

    batch_id = str(uuid.uuid4())
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            _CLAIM_CHUNK,
            {
                "engines": engines,
                "batch_size": batch_size,
                "max_file_size_bytes": max_file_size_bytes,
                "max_duration_seconds": max_duration_seconds,
            },
        )
        rows = cur.fetchall()
        claimed = list(dict.fromkeys(str(r["media_id"]) for r in rows))

    conn.commit()
    return claimed, batch_id


def _notify_chunk_ready(conn, batch_id: str, media_ids: list[str]):
    """Write orchestration_events row for Server to pick up."""
    with conn.cursor() as cur:
        cur.execute(
            _NOTIFY_EVENT,
            {
                "event_type": "chunk_ready",
                "batch_id": batch_id,
                "data": json.dumps({
                    "batch_id": batch_id,
                    "media_ids": media_ids,
                }),
            },
        )
    conn.commit()


def _wait_chunk_done(conn, media_ids: list[str], engines: list[str], timeout_minutes: int = 180) -> bool:
    """Poll ai_engine_jobs until all claimed jobs are done or timeout.

    Returns True if chunk completed successfully, False on timeout.
    """
    if not media_ids or not engines:
        return True

    deadline = time.time() + timeout_minutes * 60
    consecutive_fail = 0
    while time.time() < deadline:
        with conn.cursor() as cur:
            cur.execute(
                _CHECK_CHUNK_DONE,
                {"media_ids": media_ids, "engines": engines},
            )
            remaining = cur.fetchone()[0]
        if remaining == 0:
            logger.info("Chunk %d jobs completed", len(media_ids))
            return True
        # Check if Server and AI are still alive (early abort on crash)
        try:
            req = urllib.request.Request(f"{SERVER_SERVICE_URL}/api/ping", method="GET")
            with urllib.request.urlopen(req, timeout=3):
                pass
            req2 = urllib.request.Request(f"{AI_SERVICE_URL}/health", method="GET")
            with urllib.request.urlopen(req2, timeout=3):
                pass
        except Exception as e:
            consecutive_fail += 1
            if consecutive_fail >= 2:
                logger.warning("Chunk: service unreachable after %d checks (%s), aborting wait", consecutive_fail, e)
                return False
        time.sleep(10)

    logger.warning("Chunk timed out after %d min", timeout_minutes)
    return False


# ═════════════════════════════════════════════════════════════════════════════
# Main loop
# ═════════════════════════════════════════════════════════════════════════════

def _run_auto_schedule(conn):
    """Auto-scheduling: read config → check conditions → claim → notify → wait → loop."""
    config = _get_auto_config(conn)
    if not config:
        return

    if not _check_auto_conditions(conn, config):
        return

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

    while True:
        # Claim a chunk
        media_ids, batch_id = _claim_next_chunk(conn, config)
        if not media_ids:
            logger.info("Auto-schedule: no pending videos to claim")
            break

        logger.info("Auto-schedule: claimed %d videos, batch=%s", len(media_ids), batch_id)

        # Write event for Server
        _notify_chunk_ready(conn, batch_id, media_ids)
        logger.info("Auto-schedule: wrote chunk_ready event batch=%s", batch_id)

        # Wait for this chunk to finish
        ok = _wait_chunk_done(conn, media_ids, engines, timeout_min)

        # If timed out, continue to next auto-check cycle (recovery will handle)
        if not ok:
            logger.warning("Auto-schedule: chunk timed out batch=%s", batch_id)
            break

        # Quick re-check conditions for next chunk
        if not _check_auto_conditions(conn, config):
            logger.info("Auto-schedule: conditions no longer met, pausing")
            break

    _log_pending_summary(conn)


def _run_loop():
    """Main orchestration loop."""
    logger.info(
        "Orchestrator started (poll=%ds timeout=%dmin max_retries=%d)",
        POLL_INTERVAL,
        JOB_TIMEOUT_MINUTES,
        MAX_RETRIES,
    )

    cycle = 0
    while True:
        cycle += 1
        conn = None
        try:
            conn = _get_conn()
            conn.autocommit = False

            # 1. Recover stale running jobs (timeout detection)
            changed = _recover_stale(conn)

            # 2. Log pending summary
            pending = _log_pending_summary(conn)

            # 3. Check backlog
            with conn.cursor() as cur:
                cur.execute(_CHECK_BACKLOG)
                backlog = cur.fetchone()[0]
                cur.execute(_CHECK_RUNNING_BATCH)
                running = cur.fetchone()[0] > 0

            # 4. Auto-schedule if no batch is currently running
            if backlog > 0 and not running:
                _run_auto_schedule(conn)

        except Exception:
            logger.exception("Cycle %d failed", cycle)
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn:
                _put_conn(conn)

        # Use check_interval_seconds from PG config (set via auto tab on page) if available
        conn2 = None
        try:
            conn2 = _get_conn()
            conn2.autocommit = False
            config = _get_auto_config(conn2)
            if config and config.get("check_interval_seconds", 0) > 0:
                cycle_interval = config["check_interval_seconds"]
            else:
                cycle_interval = POLL_INTERVAL
        except Exception:
            cycle_interval = POLL_INTERVAL
        finally:
            if conn2:
                _put_conn(conn2)

        time.sleep(cycle_interval)


# ── entrypoint ───────────────────────────────────────────────────────────────

from log_setup import setup_logging


def main():
    setup_logging()
    _run_loop()


if __name__ == "__main__":
    main()
