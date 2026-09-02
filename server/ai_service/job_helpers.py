"""AI 容器唯一的状态写入口（R1.3）。

Server 容器用 ``app/core/job_helpers.py``，AI 容器用本模块。
其余代码禁止直接写 ``ai_engine_jobs`` / ``processing_state``。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_JOB_DEPS = {"clip": ["scene"], "diarization": ["transcript"], "yolo": ["scene"], "ocr": ["scene"]}


def _upsert_job(md, media_id_str: str, engine: str, status: str):
    """私有实现：upsert ai_engine_jobs 状态行。"""
    from sqlalchemy import text
    try:
        deps = _JOB_DEPS.get(engine, [])
        md.execute(
            text("""INSERT INTO ai_engine_jobs (media_id, engine_name, status, depends_on, completed_at)
                     VALUES (:mid, :eng, :st, :deps, NOW())
                     ON CONFLICT (media_id, engine_name)
                    DO UPDATE SET status = :st2, completed_at = NOW(), 
                       error_message = CASE WHEN :st2 = 'completed' THEN NULL ELSE ai_engine_jobs.error_message END"""),
            {"mid": media_id_str, "eng": engine, "st": status, "deps": deps, "st2": status},
        )
        md.commit()
    except Exception:
        logger.warning("ai_engine_jobs upsert failed for %s/%s", media_id_str, engine)


def set_job_status(media_id, engine, status):
    """公开写入口：更新单个引擎状态（自开自关 PG session）。"""
    try:
        from models.db import get_pg_session
        s = get_pg_session()
        try:
            _upsert_job(s, media_id, engine, status)
        finally:
            s.close()
    except Exception as e:
        logger.warning("Failed to set %s job status for %s: %s", engine, media_id, e)


def reset_jobs_for_asset(media_id):
    """公开写入口：把某资产全部 job 重置为 pending（reset-asset 接口用）。"""
    try:
        from models.db import get_pg_session
        from sqlalchemy import text
        pg = get_pg_session()
        pg.execute(text("UPDATE ai_engine_jobs SET status = :s, error_message = NULL, retry_count = 0, started_at = NULL, completed_at = NULL WHERE media_id = :mid"), {"s": "pending", "mid": media_id})
        pg.commit()
        pg.close()
        logger.info("Reset PG engine jobs to pending for video %s", media_id)
    except Exception as e:
        logger.warning("Failed to reset PG engine jobs for %s: %s", media_id, e)
