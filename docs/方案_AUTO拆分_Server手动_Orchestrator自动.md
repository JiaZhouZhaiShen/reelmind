# AUTO 拆分方案：手动走 Server，自动走 Orchestrator（全 API）

> 目标：手动批量管道归 Server，自动批量管道归 Orchestrator。
> Orchestrator 不再直连 PG，全部通过 Server HTTP API 操作。
> **手动和自动互斥：同一时间只有一个能运行。**

---

## 互斥保证

手动和自动最终汇聚到同一个入口：`_orchestrate_batch()`（`shared.py`）。

```python
# shared.py 第 90 行
if not _orchestration_lock.acquire(blocking=False):
    logger.warning("另一个 orchestration 正在运行，跳过")
    return None
```

| 触发方式 | 路径 | 锁 |
|---------|------|-----|
| 手动点击批量 | `start_manual_batch()` → thread → `_orchestrate_batch("manual")` | `_orchestration_lock` |
| 自动事件消费 | `start_event_scanner()` → thread → `_orchestrate_batch("auto")` | `_orchestration_lock` |

拿到锁的执行，拿不到的跳过。无需额外互斥逻辑。`_orchestrate_batch()` 自己释放锁，下一个才能进。

---

## 最终架构

```
┌─ 手动批量 ─────────────────────────────────────────┐
│                                                     │
│  UI 点"开始批量"                                    │
│    → POST /ai/pipeline/manual/start                  │
│      → _orchestrate_batch("manual", ...)  (Server)   │
│        → start_pipeline() → AI 容器                  │
│        → wait_for_completion()                       │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─ 自动批量 ─────────────────────────────────────────┐
│                                                     │
│  Orchestrator (_run_loop)                           │
│    ├─ GET  /ai/pipeline/auto/config                 │
│    ├─ GET  /ai/pipeline/auto/pending-summary         │
│    ├─ GET  <AI>/health         (GPU 检查)            │
│    ├─ POST /ai/pipeline/auto/claim                   │
│    │   └─ Server: FOR UPDATE SKIP LOCKED + 写事件    │
│    ├─ loop: GET /ai/pipeline/auto/chunk-done         │
│    └─ done → 下一轮                                  │
│                                                     │
│  Server (event_scanner 后台线程)                     │
│    └─ 轮询 orchestration_events 表                   │
│      → 读到 chunk_ready                             │
│      → _orchestrate_batch("auto", media_ids)         │
│        → start_pipeline() → AI 容器                  │
│        → wait_for_completion()                       │
│        → mark engine jobs completed                  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 改动清单

### 文件清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `server/app/api/ai/shared.py` | 删 | 移除 auto 轮询相关代码（L299-L378） |
| 2 | `server/app/api/ai/pipeline.py` | 加 | 新增 4 个 auto 管理 API 端点 |
| 3 | `server/app/api/ai/scan_events.py` | 改 | 取消 `start_event_scanner()` 的注释 |
| 4 | `server/orchestrator/main.py` | 改 | 所有 PG 操作改为 HTTP 调 Server |
| 5 | `server/orchestrator/job_ops.py` | 删 | 删除 `claim_chunk()`, `reclaim_timed_out_chunk()` |
| 6 | `server/orchestrator/requirements.txt` | 改 | 移除 `psycopg2-binary` |

---

## 步骤 1：Server — 移除 shared.py 的 auto 轮询

**文件：** `server/app/api/ai/shared.py`

**删除内容（L299-L378）：**

```python
# ── Auto-run scheduler (periodic polling, no events) ────────────────────
_auto_stop_event = threading.Event()

def _get_gpu_usage_percent() -> float:
    ...

def _in_time_window(start_hour: int, end_hour: int) -> bool:
    ...

def _auto_run_scheduler_loop():
    ...

def start_auto_polling():
    ...

# 最后一行也要删
start_auto_polling()
```

**保留：** `_orchestrate_batch()`, `_orchestration_lock`, `_mark_checkpoint_cancelled`, `_cleanup_stale_checkpoints` — 手动批量和事件消费都要用。

---

## 步骤 2：Server — 新增 4 个 auto 管理 API

**文件：** `server/app/api/ai/pipeline.py`

在 `set_auto_pipeline_config` 之后（L146 之后），`get_single_pipeline_config` 之前，插入 4 个新端点：

### 2.1 GET /pipeline/auto/pending-summary

```python
@router.get("/pipeline/auto/pending-summary")
async def get_auto_pending_summary():
    """Orchestrator 专用：返回 backlog/running 汇总。

    Orchestrator 用此替代直连 PG 的 _CHECK_BACKLOG / _CHECK_RUNNING_BATCH。
    """
    from app.database import sync_session_factory
    from app.models.ai_engine_job import AIEngineJob
    from sqlalchemy import text

    session = sync_session_factory()
    try:
        # backlog: pending jobs whose dependencies are met
        backlog = session.execute(text("""
            SELECT COUNT(*) FROM ai_engine_jobs
            WHERE status = 'pending'
              AND NOT EXISTS (
                  SELECT 1 FROM ai_engine_jobs d
                  WHERE d.media_id = ai_engine_jobs.media_id
                    AND d.engine_name = ANY(ai_engine_jobs.depends_on)
                    AND d.status != 'completed'
              )
        """)).scalar() or 0

        # running: any jobs currently running
        running = session.query(AIEngineJob).filter(
            AIEngineJob.status == "running"
        ).count()

        # total_pending: all pending
        total_pending = session.query(AIEngineJob).filter(
            AIEngineJob.status == "pending"
        ).count()

        # per-engine pending counts
        from sqlalchemy import func
        rows = session.query(
            AIEngineJob.engine_name,
            func.count(AIEngineJob.id)
        ).filter(
            AIEngineJob.status == "pending"
        ).group_by(AIEngineJob.engine_name).all()
        pending_per_engine = {r[0]: r[1] for r in rows}

        return {
            "backlog": backlog,
            "running": running,
            "total_pending": total_pending,
            "pending_per_engine": pending_per_engine,
        }
    finally:
        session.close()
```

### 2.2 POST /pipeline/auto/claim

```python
@router.post("/pipeline/auto/claim")
async def claim_auto_chunk(data: dict):
    """Orchestrator 调用：原子 claim 一个 chunk（FOR UPDATE SKIP LOCKED）。

    原 orchestrator/job_ops.py:claim_chunk() 的逻辑搬到 Server。
    同时写 chunk_ready 事件到 orchestration_events，让事件消费者处理。
    """
    from app.database import sync_session_factory
    from app.models.ai_engine_job import AIEngineJob, ENGINE_NAMES
    from app.models.asset import Asset
    from app.models.orchestration_event import OrchestrationEvent
    from sqlalchemy import text as _text, and_
    import uuid

    engines = data.get("engines", list(ENGINE_NAMES))
    batch_size = data.get("batch_size", 50)
    filters = data.get("filters", {})
    max_file_size_mb = filters.get("max_file_size_mb", 0)
    max_duration_minutes = filters.get("max_duration_minutes", 0)
    max_file_size_bytes = max_file_size_mb * 1024 * 1024 if max_file_size_mb > 0 else 0
    max_duration_seconds = max_duration_minutes * 60 if max_duration_minutes > 0 else 0

    batch_id = str(uuid.uuid4())

    session = sync_session_factory()
    try:
        _CLAIM_SQL = _text("""
            WITH eligible_media AS (
                SELECT DISTINCT j.media_id
                FROM ai_engine_jobs j
                JOIN assets a ON a.id = j.media_id
                WHERE j.status = 'pending'
                  AND j.engine_name = ANY(:engines)
                  AND NOT EXISTS (
                      SELECT 1 FROM ai_engine_jobs d
                      WHERE d.media_id = j.media_id
                        AND d.engine_name = ANY(j.depends_on)
                        AND d.status != 'completed'
                  )
                  AND a.file_size IS NOT NULL AND a.file_size > 0
                  AND (:max_file_size_bytes <= 0 OR a.file_size <= :max_file_size_bytes)
                  AND (:max_duration_seconds <= 0
                      OR (a.duration IS NOT NULL AND a.duration > 0 AND a.duration <= :max_duration_seconds))
                ORDER BY j.media_id
                LIMIT :batch_size
            ),
            eligible AS (
                SELECT j.media_id
                FROM ai_engine_jobs j
                WHERE j.media_id IN (SELECT media_id FROM eligible_media)
                  AND j.status = 'pending'
                  AND j.engine_name = ANY(:engines)
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
              AND ai_engine_jobs.engine_name = ANY(:engines)
            RETURNING ai_engine_jobs.media_id
        """)
        rows = session.execute(
            _CLAIM_SQL,
            {
                "engines": engines,
                "batch_size": batch_size,
                "max_file_size_bytes": max_file_size_bytes,
                "max_duration_seconds": max_duration_seconds,
            }
        ).fetchall()
        claimed = list(dict.fromkeys(str(r[0]) for r in rows))

        if not claimed:
            session.close()
            return {"claimed": False, "batch_id": batch_id, "media_ids": []}

        # 写 chunk_ready 事件（事件消费者会调 _orchestrate_batch）
        event = OrchestrationEvent(
            event_type="chunk_ready",
            batch_id=uuid.UUID(batch_id),
            data={"batch_id": batch_id, "media_ids": claimed},
        )
        session.add(event)
        session.commit()

        logger.info(
            "claim_auto_chunk: batch=%s media_ids=%d",
            batch_id, len(claimed),
        )
        return {
            "claimed": True,
            "batch_id": batch_id,
            "media_ids": claimed,
        }
    except Exception:
        logger.exception("claim_auto_chunk failed")
        session.rollback()
        return {"claimed": False, "batch_id": batch_id, "media_ids": []}
    finally:
        session.close()
```

### 2.3 GET /pipeline/auto/chunk-done

```python
@router.get("/pipeline/auto/chunk-done")
async def check_chunk_done(
    batch_id: str = Query(...),
    engines: str = Query(None),
):
    """Orchestrator 轮询：检查一个 chunk 是否处理完成。

    查询 ai_engine_jobs 看 batch 的 media_ids 中是否还有未完成的 job。
    batch_id 对应 orchestration_events 中的批次。
    """
    from app.database import sync_session_factory
    from app.models.orchestration_event import OrchestrationEvent
    from app.models.ai_engine_job import AIEngineJob
    from sqlalchemy import text as _text
    import uuid

    try:
        uid = uuid.UUID(batch_id)
    except ValueError:
        return {"error": "invalid batch_id"}

    session = sync_session_factory()
    try:
        # 从事件数据中取 media_ids
        event = session.query(OrchestrationEvent).filter(
            OrchestrationEvent.batch_id == uid,
            OrchestrationEvent.event_type == "chunk_ready",
        ).first()
        if not event:
            return {"error": "batch_id not found", "done": True}

        media_ids = (event.data or {}).get("media_ids", [])
        if not media_ids:
            return {"done": True, "remaining": 0}

        engine_list = engines.split(",") if engines else []

        remaining = session.query(AIEngineJob).filter(
            AIEngineJob.media_id.in_(media_ids),
            AIEngineJob.status.notin_(["completed", "error", "cancelled"]),
        )
        if engine_list:
            remaining = remaining.filter(AIEngineJob.engine_name.in_(engine_list))
        remaining_count = remaining.count()

        return {"done": remaining_count == 0, "remaining": remaining_count}
    finally:
        session.close()
```

### 2.4 POST /pipeline/auto/reclaim

```python
@router.post("/pipeline/auto/reclaim")
async def reclaim_timed_out_chunk(data: dict):
    """Orchestrator 调用：超时后把 chunk 的 jobs 重置回 pending。

    原 orchestrator/job_ops.py:reclaim_timed_out_chunk() 的逻辑搬到 Server。
    """
    from app.database import sync_session_factory
    from app.models.ai_engine_job import AIEngineJob

    media_ids = data.get("media_ids", [])
    engines = data.get("engines", [])

    if not media_ids:
        return {"reclaimed": 0}

    session = sync_session_factory()
    try:
        q = session.query(AIEngineJob).filter(
            AIEngineJob.media_id.in_(media_ids),
            AIEngineJob.status == "running",
        )
        if engines:
            q = q.filter(AIEngineJob.engine_name.in_(engines))

        count = q.update({
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "error_message": "reclaimed from timed-out chunk",
        })
        session.commit()
        logger.info("reclaim_timed_out_chunk: reclaimed %d jobs", count)
        return {"reclaimed": count}
    except Exception:
        logger.exception("reclaim_timed_out_chunk failed")
        session.rollback()
        return {"reclaimed": 0}
    finally:
        session.close()
```

---

## 步骤 3：Server — 打开事件消费者

**文件：** `server/app/api/ai/scan_events.py`

**L104 改：**

```python
# 改前
# start_event_scanner() removed - auto polling runs via shared.py

# 改后
start_event_scanner()
```

事件消费者（L52-101）逻辑已完整，无需修改：
- 每 5s 轮询 `orchestration_events` 表
- 读到 `chunk_ready` → 标记 consumed
- 调 `_orchestrate_batch("auto", auto_config, None, media_ids)` → 发 AI

---

## 步骤 4：Orchestrator — 全部改为 HTTP API 调用

**文件：** `server/orchestrator/main.py`

### 4.1 移除 import

删掉：
```python
import psycopg2
import psycopg2.extras
import psycopg2.pool
import zoneinfo
```

保留：
```python
import datetime
import logging
import os
import sys
import time
import uuid
import json
import urllib.request
```

### 4.2 移除 DB 配置

删掉：
```python
DB_HOST = os.environ.get(...)
DB_PORT = os.environ.get(...)
DB_USER = os.environ.get(...)
DB_PASSWORD = os.environ.get(...)
DB_NAME = os.environ.get(...)
```

删掉 `_pool` 和 `_get_conn()` / `_put_conn()`。

### 4.3 删除所有 SQL 常量

删掉：
```python
_RECOVER_STALE = """..."""
_RECOVER_EXHAUSTED = """..."""
_COUNT_PENDING = """..."""
_CHECK_BACKLOG = """..."""
_CHECK_RUNNING_BATCH = """..."""
_GET_AUTO_CONFIG = """..."""
_CLAIM_CHUNK = """..."""
_CHECK_CHUNK_DONE = """..."""
_NOTIFY_EVENT = """..."""
_RECLAIM_TIMED_OUT_CHUNK = """..."""
```

### 4.4 新增 HTTP helper

```python
SERVER_URL = os.environ.get("ORCHESTRATOR_SERVER_URL", "http://reelmind-server:2588")

def _server_get(path: str) -> dict | None:
    """GET 调 Server API."""
    try:
        req = urllib.request.Request(f"{SERVER_URL}/api{path}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.warning("Server GET %s failed: %s", path, e)
        return None

def _server_post(path: str, data: dict) -> dict | None:
    """POST 调 Server API."""
    try:
        body = json.dumps(data).encode()
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
```

### 4.5 重写 _recover_stale

改为调 Server API（沿用已有的 `POST /ai/pipeline/jobs/reset-errors` 端点）：

```python
def _recover_stale():
    """通过 Server API 恢复超时/错误 jobs."""
    # 重置所有状态为 error 的 jobs 回 pending
    result = _server_post("/ai/pipeline/jobs/reset-errors", {})
    if result:
        count = result.get("count", 0)
        if count:
            logger.info("Recovered %d error jobs via Server API", count)
        return count
    return 0
```

### 4.6 重写 _log_pending_summary

```python
def _log_pending_summary():
    """通过 Server API 获取 pending 汇总并打日志."""
    result = _server_get("/ai/pipeline/auto/pending-summary")
    if result:
        total = result.get("total_pending", 0)
        per_engine = result.get("pending_per_engine", {})
        if total:
            parts = ", ".join(f"{k}={v}" for k, v in sorted(per_engine.items()))
            logger.info("Pending: %d total [%s]", total, parts)
        return total
    return 0
```

### 4.7 重写 _get_auto_config

```python
def _get_auto_config() -> dict | None:
    """通过 Server API 读取 auto pipeline 配置."""
    result = _server_get("/ai/pipeline/auto/config")
    if result:
        return result.get("config")
    return None
```

### 4.8 重写 _check_auto_conditions

```python
def _check_auto_conditions(config: dict) -> bool:
    """检查 auto 条件（全 API，不直连 PG）。"""
    if not config.get("enabled", False):
        return False

    # 时间窗口
    start_h = config.get("time_window_start", 0)
    end_h = config.get("time_window_end", 6)
    current_hour = datetime.datetime.now().hour
    if start_h <= end_h:
        if not (start_h <= current_hour < end_h):
            return False
    else:
        # 跨午夜
        if not (current_hour >= start_h or current_hour < end_h):
            return False

    # 通过 Server API 检查 backlog 和 running
    summary = _server_get("/ai/pipeline/auto/pending-summary")
    if not summary:
        return False
    if summary.get("backlog", 0) == 0:
        return False
    if summary.get("running", 0) > 0:
        return False

    # 检查 GPU
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
        return False

    return True
```

### 4.9 重写 _run_auto_schedule

```python
def _run_auto_schedule():
    """通过 Server API 完成一个完整的 auto 调度周期。"""
    config = _get_auto_config()
    if not config:
        return

    if not _check_auto_conditions(config):
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
        # Claim chunk via Server API
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

        # Wait for chunk to complete (poll Server API)
        deadline = time.time() + timeout_min * 60
        consecutive_fail = 0
        while time.time() < deadline:
            status = _server_get(f"/ai/pipeline/auto/chunk-done?batch_id={batch_id}")
            if status and status.get("done"):
                remaining = status.get("remaining", 0)
                if remaining == 0:
                    logger.info("Auto-schedule: chunk %s completed", batch_id)
                    break

            # Check if Server and AI are still alive
            try:
                req = urllib.request.Request(f"{SERVER_URL}/api/ping", method="GET")
                with urllib.request.urlopen(req, timeout=3): pass
                req2 = urllib.request.Request(f"{AI_SERVICE_URL}/health", method="GET")
                with urllib.request.urlopen(req2, timeout=3): pass
                consecutive_fail = 0
            except Exception as e:
                consecutive_fail += 1
                if consecutive_fail >= 2:
                    logger.warning("Chunk: service unreachable after %d checks (%s), aborting wait", consecutive_fail, e)
                    break

            time.sleep(10)
        else:
            # Timed out
            logger.warning("Auto-schedule: chunk timed out batch=%s", batch_id)
            _server_post("/ai/pipeline/auto/reclaim", {
                "media_ids": media_ids,
                "engines": engines,
            })
            break

        # Quick re-check conditions for next chunk
        if not _check_auto_conditions(config):
            logger.info("Auto-schedule: conditions no longer met, pausing")
            break

    _log_pending_summary()
```

### 4.10 重写 _run_loop

```python
def _run_loop():
    logger.info(
        "Orchestrator started (API mode, poll=%ds timeout=%dmin)",
        POLL_INTERVAL, JOB_TIMEOUT_MINUTES,
    )

    cycle = 0
    while True:
        cycle += 1
        try:
            # 1. Recover stale/error jobs via Server API
            changed = _recover_stale()

            # 2. Log pending summary via Server API
            pending = _log_pending_summary()

            # 3. Auto-schedule via Server API (if conditions met)
            if pending > 0:
                _run_auto_schedule()

        except Exception:
            logger.exception("Cycle %d failed", cycle)

        time.sleep(POLL_INTERVAL)
```

### 4.11 删除删除 `from job_ops import ...`

改：
```python
# 改前
from job_ops import recover_stale, recover_exhausted, claim_chunk, reclaim_timed_out_chunk

# 改后
# 不再需要 import job_ops
```

---

## 步骤 5：删除 orchestrator/job_ops.py

删除整个 `server/orchestrator/job_ops.py`（`claim_chunk()`, `reclaim_timed_out_chunk()`, `recover_stale()`, `recover_exhausted()` 已全部迁移到 Server API）。

---

## 步骤 6：精简 orchestrator/requirements.txt

```txt
# 改前
psycopg2-binary==2.9.9

# 改后
# 仅依赖 Python 标准库 urllib.request，无需额外包
# 此行可空或删除
```

Dockerfile 无需修改，`pip install` 空 requirements.txt 无副作用。

---

## 验证清单

### 功能验证

```
[ ] 打开 /ai 页面，手动管道的配置（引擎/批大小/过滤器）可正常保存
[ ] 点"开始批量处理"→ Server 启动 _orchestrate_batch → AI 正常处理
[ ] 自动管道的配置（开关/时间窗口/GPU阈值/引擎/过滤器）可正常保存
[ ] Orchestrator 日志显示: 读配置 → 检查条件 → claim chunk → 等完成
[ ] AI 容器收到 Orchestrator claim 的 chunk 并正常处理
[ ] 处理完后 engine jobs 正常标记 completed
```

### 回归验证

```
[ ] Server 的 _orchestrate_batch() 还能正常工作（手动批量 + 事件消费）
[ ] Orchestrator 不再直连 PG（无 psycopg2、无 DB 配置）
[ ] container 删了重建秒起，不丢失状态
[ ] 前端 AI 页面展示的 pending/success/error 数据正常
[ ] 两套同时触发不会冲突（_orchestration_lock 防重入）
```

### 文件清理验证

```
[ ] shared.py 中无 _auto_run_scheduler_loop / start_auto_polling 残留
[ ] orchestrator/main.py 中无 psycopg2 import 或 PG SQL 残留
[ ] orchestrator/job_ops.py 已删除
[ ] scan_events.py L104 start_event_scanner() 已取消注释
```
