#!/bin/bash
set -e

echo "==> ReelMind AI entrypoint: starting Celery worker (background) + Uvicorn (foreground)"

export PYTHONPATH=/server:$PYTHONPATH

# 后台起 celery worker（收扫描/缩略图任务）
celery -A app.worker.celery_app worker -Q celery,default \
  --loglevel=${CELERY_LOGLEVEL:-info} \
  --concurrency=${CELERY_CONCURRENCY:-4} \
  --max-tasks-per-child=${CELERY_MAX_TASKS:-10} \
  --prefetch-multiplier=${CELERY_PREFETCH:-1} &

# 前台起 uvicorn（AI 管线 API）
 exec uvicorn main:app --host 0.0.0.0 --port 2589 --workers 1
